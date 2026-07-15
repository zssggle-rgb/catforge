"""G35 deterministic ranking, comparison roles, and priority selection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
    COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
    COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION,
    CandidateScopeAssessment,
    PairGateEvaluation,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
    PairAnalysisAssembly,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    PRIMARY_DIMENSION_WEIGHTS,
    PRIMARY_SCORE_DIMENSIONS,
    ComparisonRole,
    CompetitorProfileV11BaseModel,
    ConclusionStrength,
    DimensionAvailability,
    PairScoreBreakdown,
    PairScoreComponent,
    ScorePolicyComponent,
    ScorePolicyContract,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMPETITOR_PROFILE_V1_1_SELECTION_METHOD_VERSION = "competitor_profile_v1_1_selector_v1"
COMPETITOR_PROFILE_V1_1_SELECTION_CONFIG_VERSION = (
    "question_strength_score_diversity_v1"
)
MAX_PRIORITY_COMPETITORS = 3

_QUESTION_PRIORITY = (
    "purchase_choice",
    "value_substitution",
    "price_ladder_defense",
    "scenario_solution",
    "same_brand_portfolio_role",
    "configuration_follow",
    "price_volume_pressure",
)
_QUESTION_PRIORITY_INDEX = {
    code: index for index, code in enumerate(_QUESTION_PRIORITY)
}
_STRENGTH_RANK = {
    ConclusionStrength.UNKNOWN.value: 0,
    ConclusionStrength.REFERENCE.value: 1,
    ConclusionStrength.DIRECTIONAL.value: 2,
    ConclusionStrength.SUPPORTED.value: 3,
    ConclusionStrength.STRONG.value: 4,
}
_ROLE_PRIORITY = (
    ComparisonRole.DIRECT_COMPETITOR.value,
    ComparisonRole.PRICE_ADJACENT.value,
    ComparisonRole.DOWNTRADE_DIVERSION.value,
    ComparisonRole.UPTRADE_ALTERNATIVE.value,
    ComparisonRole.SAME_BRAND_LADDER.value,
    ComparisonRole.SCENARIO_ALTERNATIVE.value,
    ComparisonRole.VALUE_SUBSTITUTE.value,
    ComparisonRole.CONFIGURATION_BENCHMARK.value,
    ComparisonRole.MARKET_REFERENCE.value,
)
_ROLE_PRIORITY_INDEX = {code: index for index, code in enumerate(_ROLE_PRIORITY)}
_RELATION_ROLE = {
    "direct_substitute": ComparisonRole.DIRECT_COMPETITOR.value,
    "same_budget_alternative": ComparisonRole.PRICE_ADJACENT.value,
    "downtrade_diversion": ComparisonRole.DOWNTRADE_DIVERSION.value,
    "uptrade_alternative": ComparisonRole.UPTRADE_ALTERNATIVE.value,
    "same_brand_ladder": ComparisonRole.SAME_BRAND_LADDER.value,
    "scenario_substitute": ComparisonRole.SCENARIO_ALTERNATIVE.value,
    "same_value_substitute": ComparisonRole.VALUE_SUBSTITUTE.value,
}
_QUESTION_ROLE = {
    "purchase_choice": ComparisonRole.DIRECT_COMPETITOR.value,
    "value_substitution": ComparisonRole.VALUE_SUBSTITUTE.value,
    "same_brand_portfolio_role": ComparisonRole.SAME_BRAND_LADDER.value,
    "scenario_solution": ComparisonRole.SCENARIO_ALTERNATIVE.value,
    "configuration_follow": ComparisonRole.CONFIGURATION_BENCHMARK.value,
    "price_volume_pressure": ComparisonRole.MARKET_REFERENCE.value,
}
_SELECTION_REASON_CN = {
    "highest_supported_priority": "综合结论强度和六维排序领先，作为首要重点竞品。",
    "adds_decision_role_coverage": "补充了已选候选尚未覆盖的产品决策角色，进入重点竞品。",
    "next_strongest_priority": "在剩余候选中结论与六维排序领先，进入重点竞品。",
    "no_answerable_product_question": "当前证据不能独立回答产品决策问题，保留完整分析但不进入重点名单。",
    "stronger_candidate_covers_same_decision_role": "已有结论更强的候选覆盖相同决策角色，本候选保留完整比较但不进入重点名单。",
    "priority_capacity_reached": "本候选具备独立决策价值，但重点名单已由更优或互补候选占用。",
}


class CompetitorSelectionInputError(RuntimeError):
    """Raised when G33/G34 inputs do not form one immutable selection universe."""


class LegacyTopCompetitorReference(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    legacy_rank: int = Field(ge=1, le=3)
    legacy_role: str | None = None


class PairSelectionInput(CompetitorProfileV11BaseModel):
    assembly: PairAnalysisAssembly | None = None
    gate_evaluation: PairGateEvaluation
    legacy_rank: int | None = Field(default=None, ge=1, le=3)
    legacy_role: str | None = None

    @model_validator(mode="after")
    def validate_input(self) -> "PairSelectionInput":
        analyzable = self.gate_evaluation.scope.scope_status == "analyzable"
        if analyzable != (self.assembly is not None):
            raise ValueError(
                "analyzable selection inputs require an assembly; excluded inputs forbid it"
            )
        return self


class PairSelectionDecision(CompetitorProfileV11BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    competitor_profile_version_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str | None = None
    scope_status: Literal["analyzable", "excluded"]
    exclusion_reason_code: str | None = None
    score_breakdown: PairScoreBreakdown | None = None
    comparison_roles: list[ComparisonRole] = Field(default_factory=list)
    primary_role: ComparisonRole | None = None
    answerable_question_codes: list[str] = Field(default_factory=list)
    selection_conclusion_strength: ConclusionStrength
    selection_eligible: StrictBool
    selected: StrictBool
    selection_rank: int | None = Field(default=None, ge=1, le=3)
    selection_reason_code: str = Field(min_length=1)
    selection_reason_cn: str = Field(min_length=1)
    market_validation_strength: ConclusionStrength
    recall_rank: int | None = Field(default=None, ge=1)
    legacy_rank: int | None = Field(default=None, ge=1, le=3)
    legacy_role: str | None = None
    review_required: StrictBool = False
    assembly_result_hash: str | None = None
    gate_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> "PairSelectionDecision":
        roles = [str(row) for row in self.comparison_roles]
        if roles != sorted(set(roles), key=_ROLE_PRIORITY_INDEX.__getitem__):
            raise ValueError(
                "comparison roles must be unique and follow frozen priority"
            )
        if (
            self.primary_role is not None
            and self.primary_role not in self.comparison_roles
        ):
            raise ValueError("primary role must be included in comparison roles")
        if self.answerable_question_codes != sorted(
            set(self.answerable_question_codes),
            key=_QUESTION_PRIORITY_INDEX.__getitem__,
        ):
            raise ValueError("answerable questions must follow frozen product priority")
        if self.scope_status == "excluded":
            if self.score_breakdown is not None or self.selection_eligible:
                raise ValueError(
                    "hard-excluded candidates cannot be scored or selected"
                )
            if self.comparison_roles or self.primary_role is not None:
                raise ValueError(
                    "hard-excluded candidates cannot carry comparison roles"
                )
            if self.assembly_result_hash is not None or self.recall_rank is not None:
                raise ValueError("hard-excluded candidates cannot claim pair analysis")
        elif self.score_breakdown is None or self.assembly_result_hash is None:
            raise ValueError("analyzable candidates require a complete score process")
        if self.selection_eligible != bool(self.answerable_question_codes):
            raise ValueError(
                "selection eligibility must equal answerable product questions"
            )
        if self.selection_eligible == (
            self.selection_conclusion_strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError("only non-unknown product conclusions may enter selection")
        if self.selected:
            if not self.selection_eligible or self.selection_rank is None:
                raise ValueError("selected competitors must be eligible and ranked")
        elif self.selection_rank is not None:
            raise ValueError("unselected candidates cannot carry a selection rank")
        return self


class PrioritySelectionPlan(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    selection_rank: int = Field(ge=1, le=3)
    primary_role: ComparisonRole
    role_codes: list[ComparisonRole] = Field(min_length=1)
    answerable_question_codes: list[str] = Field(min_length=1)
    selection_score: Decimal = Field(ge=0, le=1)
    selection_available_weight: Decimal = Field(ge=0, le=1)
    selection_conclusion_strength: ConclusionStrength
    selection_reason_code: str = Field(min_length=1)
    selection_reason_cn: str = Field(min_length=1)
    pair_selection_result_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_plan(self) -> "PrioritySelectionPlan":
        roles = [str(row) for row in self.role_codes]
        if roles != sorted(set(roles), key=_ROLE_PRIORITY_INDEX.__getitem__):
            raise ValueError("priority roles must be unique and ordered")
        if self.primary_role not in self.role_codes:
            raise ValueError("priority roles must include the primary role")
        if self.selection_conclusion_strength == ConclusionStrength.UNKNOWN.value:
            raise ValueError("unknown conclusions cannot become priority competitors")
        return self


class LegacySelectionDiff(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    legacy_rank: int | None = Field(default=None, ge=1, le=3)
    new_rank: int | None = Field(default=None, ge=1, le=3)
    diff_status: Literal["retained", "added", "dropped"]
    reason_code: str = Field(min_length=1)
    reason_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_diff(self) -> "LegacySelectionDiff":
        expected = (
            "retained"
            if self.legacy_rank is not None and self.new_rank is not None
            else "dropped"
            if self.legacy_rank is not None
            else "added"
        )
        if self.diff_status != expected:
            raise ValueError("legacy selection diff status does not match its ranks")
        return self


class CompetitorSelectionResult(CompetitorProfileV11BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    competitor_profile_version_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    score_policy: ScorePolicyContract
    pair_decisions: list[PairSelectionDecision]
    priority_competitors: list[PrioritySelectionPlan] = Field(default_factory=list)
    role_buckets: dict[str, list[str]] = Field(default_factory=dict)
    legacy_selection_diffs: list[LegacySelectionDiff] = Field(default_factory=list)
    analysis_candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0, le=3)
    method_version: Literal["competitor_profile_v1_1_selector_v1"] = (
        COMPETITOR_PROFILE_V1_1_SELECTION_METHOD_VERSION
    )
    config_version: Literal["question_strength_score_diversity_v1"] = (
        COMPETITOR_PROFILE_V1_1_SELECTION_CONFIG_VERSION
    )
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "CompetitorSelectionResult":
        decision_codes = [row.candidate_sku_code or "" for row in self.pair_decisions]
        if decision_codes != sorted(decision_codes) or len(decision_codes) != len(
            set(decision_codes)
        ):
            raise ValueError("pair selection decisions must be unique and SKU ordered")
        ranks = [row.selection_rank for row in self.priority_competitors]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("priority selection ranks must be contiguous")
        selected_from_decisions = [
            (row.candidate_sku_code, row.selection_rank)
            for row in self.pair_decisions
            if row.selected
        ]
        selected_from_plans = [
            (row.candidate_sku_code, row.selection_rank)
            for row in self.priority_competitors
        ]
        if sorted(selected_from_decisions) != sorted(selected_from_plans):
            raise ValueError("priority plans must match selected pair decisions")
        if self.selected_count != len(self.priority_competitors):
            raise ValueError("selected count must match priority plans")
        if self.analysis_candidate_count != sum(
            row.scope_status == "analyzable" for row in self.pair_decisions
        ):
            raise ValueError("analysis candidate count must match analyzable decisions")
        for role, codes in self.role_buckets.items():
            if role not in _ROLE_PRIORITY or codes != sorted(set(codes)):
                raise ValueError("role buckets must use known roles and sorted SKUs")
        diff_codes = [row.candidate_sku_code for row in self.legacy_selection_diffs]
        if diff_codes != sorted(set(diff_codes)):
            raise ValueError("legacy selection diffs must be unique and SKU ordered")
        return self


@dataclass(frozen=True)
class _CandidateDraft:
    source: PairSelectionInput
    score_breakdown: PairScoreBreakdown | None
    roles: tuple[str, ...]
    primary_role: str | None
    answerable_questions: tuple[str, ...]
    selection_strength: str
    selection_eligible: bool
    market_strength: str
    recall_rank: int | None
    legacy_rank: int | None
    legacy_role: str | None
    input_fingerprint: str


class CompetitorProfileV11Selector:
    """Rank every candidate, preserve roles, and choose at most three priorities."""

    def select(
        self,
        pair_inputs: Sequence[PairSelectionInput],
        *,
        legacy_top3: Sequence[LegacyTopCompetitorReference] = (),
        verify_assembly_hashes: bool = True,
    ) -> CompetitorSelectionResult:
        if not pair_inputs:
            raise CompetitorSelectionInputError(
                "selection requires the complete candidate universe"
            )
        _assert_legacy_top3(legacy_top3)
        _assert_selection_universe(pair_inputs, legacy_top3)
        score_policy = _score_policy()
        legacy_by_sku = {row.candidate_sku_code: row for row in legacy_top3}
        drafts = [
            _analyze_pair(
                row,
                score_policy=score_policy,
                legacy_reference=legacy_by_sku.get(
                    row.gate_evaluation.candidate_sku_code or ""
                ),
                verify_assembly_hash=verify_assembly_hashes,
            )
            for row in pair_inputs
        ]
        picked = _select_priority_drafts(drafts)
        pick_by_sku = {
            draft.source.gate_evaluation.candidate_sku_code: (rank, reason)
            for rank, (draft, reason) in enumerate(picked, start=1)
        }
        covered_questions = {
            question
            for draft, _ in picked
            if (question := _draft_primary_question(draft)) is not None
        }
        covered_roles = {
            draft.primary_role for draft, _ in picked if draft.primary_role is not None
        }
        decisions = [
            _finalize_decision(
                draft,
                picked=pick_by_sku.get(draft.source.gate_evaluation.candidate_sku_code),
                covered_questions=covered_questions,
                covered_roles=covered_roles,
            )
            for draft in drafts
        ]
        decisions.sort(key=lambda row: row.candidate_sku_code or "")
        priority = _priority_plans(decisions)
        role_buckets = _role_buckets(decisions)
        legacy_diffs = _legacy_diffs(decisions, legacy_top3)
        first_gate = pair_inputs[0].gate_evaluation
        input_fingerprint = stable_hash(
            {
                "pair_input_hashes": {
                    row.candidate_sku_code or "": row.input_fingerprint
                    for row in decisions
                },
                "legacy_top3": [
                    row.model_dump(mode="json")
                    for row in sorted(legacy_top3, key=lambda item: item.legacy_rank)
                ],
                "score_policy": score_policy.model_dump(mode="json"),
                "method_version": COMPETITOR_PROFILE_V1_1_SELECTION_METHOD_VERSION,
                "config_version": COMPETITOR_PROFILE_V1_1_SELECTION_CONFIG_VERSION,
            },
            version="competitor_profile_v1_1_selection_input_v1",
        )
        result_payload = {
            "input_fingerprint": input_fingerprint,
            "pair_decision_hashes": {
                row.candidate_sku_code or "": row.result_hash for row in decisions
            },
            "priority_hashes": [row.result_hash for row in priority],
            "role_buckets": role_buckets,
            "legacy_selection_diffs": [
                row.model_dump(mode="json") for row in legacy_diffs
            ],
        }
        return CompetitorSelectionResult(
            project_id=first_gate.project_id,
            category_code=first_gate.category_code,
            competitor_profile_version_id=first_gate.competitor_profile_version_id,
            release_scope_key=first_gate.release_scope_key,
            target_sku_code=first_gate.target_sku_code,
            score_policy=score_policy,
            pair_decisions=decisions,
            priority_competitors=priority,
            role_buckets=role_buckets,
            legacy_selection_diffs=legacy_diffs,
            analysis_candidate_count=sum(
                row.scope_status == "analyzable" for row in decisions
            ),
            selected_count=len(priority),
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_v1_1_selection_result_v1",
            ),
        )


def _score_policy() -> ScorePolicyContract:
    return ScorePolicyContract(
        components=[
            ScorePolicyComponent(
                dimension_code=code,
                weight=PRIMARY_DIMENSION_WEIGHTS[code],
            )
            for code in PRIMARY_SCORE_DIMENSIONS
        ]
    )


def _analyze_pair(
    source: PairSelectionInput,
    *,
    score_policy: ScorePolicyContract,
    legacy_reference: LegacyTopCompetitorReference | None,
    verify_assembly_hash: bool,
) -> _CandidateDraft:
    gate = source.gate_evaluation
    if gate.scope.scope_status == "excluded":
        _assert_gate_hash(gate, assembly=None)
        input_fingerprint = stable_hash(
            {
                "gate_result_hash": gate.result_hash,
                "legacy_reference": (
                    legacy_reference.model_dump(mode="json")
                    if legacy_reference
                    else None
                ),
                "score_policy": score_policy.model_dump(mode="json"),
            },
            version="competitor_profile_v1_1_pair_selection_input_v1",
        )
        return _CandidateDraft(
            source=source,
            score_breakdown=None,
            roles=(),
            primary_role=None,
            answerable_questions=(),
            selection_strength=ConclusionStrength.UNKNOWN.value,
            selection_eligible=False,
            market_strength=ConclusionStrength.UNKNOWN.value,
            recall_rank=None,
            legacy_rank=(legacy_reference.legacy_rank if legacy_reference else None),
            legacy_role=(legacy_reference.legacy_role if legacy_reference else None),
            input_fingerprint=input_fingerprint,
        )
    assembly = source.assembly
    if assembly is None:
        raise CompetitorSelectionInputError(
            "analyzable selection input is missing its G33 assembly"
        )
    if verify_assembly_hash:
        _assert_assembly_hash(assembly)
    _assert_assembly_gate_authority(assembly, gate)
    _assert_gate_hash(gate, assembly=assembly)
    score = _score_pair(assembly, gate)
    questions = tuple(
        code for code in _QUESTION_PRIORITY if code in gate.answerable_question_codes
    )
    strength_by_question = {
        str(row.question_code): str(row.conclusion_strength)
        for row in gate.business_questions
    }
    selection_strength = (
        max(
            (strength_by_question[code] for code in questions),
            key=_STRENGTH_RANK.__getitem__,
        )
        if questions
        else ConclusionStrength.UNKNOWN.value
    )
    roles = tuple(_comparison_roles(assembly, gate, questions))
    primary_role = _primary_role(assembly, gate, questions, roles)
    input_fingerprint = stable_hash(
        {
            "assembly_result_hash": assembly.result_hash,
            "gate_result_hash": gate.result_hash,
            "legacy_reference": (
                legacy_reference.model_dump(mode="json") if legacy_reference else None
            ),
            "score_policy": score_policy.model_dump(mode="json"),
        },
        version="competitor_profile_v1_1_pair_selection_input_v1",
    )
    return _CandidateDraft(
        source=source,
        score_breakdown=score,
        roles=roles,
        primary_role=primary_role,
        answerable_questions=questions,
        selection_strength=selection_strength,
        selection_eligible=bool(questions),
        market_strength=str(assembly.market_validation.market_validation_strength),
        recall_rank=assembly.recall_rank,
        legacy_rank=(legacy_reference.legacy_rank if legacy_reference else None),
        legacy_role=(legacy_reference.legacy_role if legacy_reference else None),
        input_fingerprint=input_fingerprint,
    )


def _score_pair(
    assembly: PairAnalysisAssembly,
    gate: PairGateEvaluation,
) -> PairScoreBreakdown:
    states = {str(row.dimension_code): row for row in gate.dimension_states}
    score_sources = {
        "purchase_pool": assembly.purchase_pool.score,
        "battlefield_overlap": assembly.dimensions.battlefield_overlap.score,
        "user_task_overlap": assembly.dimensions.user_task_overlap.score,
        "target_group_overlap": assembly.dimensions.target_group_overlap.score,
        "value_anchor": assembly.value_anchor_analysis.score,
        "replacement_pressure": assembly.replacement_pressure_analysis.score,
    }
    components = []
    for code in PRIMARY_SCORE_DIMENSIONS:
        state = states[code]
        source_score = score_sources[code]
        unavailable = str(state.availability) in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable:
            raw_score = None
            contribution = Decimal("0")
        else:
            raw_score = source_score.normalized_score
            if raw_score is None:
                raise CompetitorSelectionInputError(
                    f"available selection dimension {code} has no normalized score"
                )
            contribution = raw_score * PRIMARY_DIMENSION_WEIGHTS[code]
        components.append(
            PairScoreComponent(
                dimension_code=code,
                availability=state.availability,
                weight=PRIMARY_DIMENSION_WEIGHTS[code],
                raw_score=raw_score,
                weighted_contribution=contribution,
            )
        )
    raw_total = sum((row.weighted_contribution for row in components), Decimal("0"))
    available_weight = sum(
        (
            row.weight
            for row in components
            if str(row.availability)
            not in {
                DimensionAvailability.UNKNOWN.value,
                DimensionAvailability.CONFLICT.value,
            }
        ),
        Decimal("0"),
    )
    normalized = raw_total / available_weight if available_weight else None
    return PairScoreBreakdown(
        components=components,
        raw_total=raw_total,
        available_weight=available_weight,
        normalized_total=normalized,
        coverage=available_weight,
        ranking_score=normalized,
        ranking_tiebreakers=[
            "market_validation_strength",
            "available_weight",
            "recall_rank",
            "candidate_sku_code",
        ],
        legacy_competitor_score=assembly.legacy_basis.competitor_score,
        legacy_payload=assembly.legacy_basis.legacy_payload,
    )


def _comparison_roles(
    assembly: PairAnalysisAssembly,
    gate: PairGateEvaluation,
    questions: Sequence[str],
) -> list[str]:
    roles = {
        _RELATION_ROLE[str(row.relation_code)]
        for row in gate.relation_assessments
        if str(row.status) in {"passed", "limited"}
        and str(row.conclusion.direction) == "positive_pressure"
    }
    roles.update(_QUESTION_ROLE[code] for code in questions if code in _QUESTION_ROLE)
    if "price_ladder_defense" in questions:
        roles.add(_price_ladder_role(assembly))
    return sorted(roles, key=_ROLE_PRIORITY_INDEX.__getitem__)


def _price_ladder_role(assembly: PairAnalysisAssembly) -> str:
    ratio = assembly.market_validation.price_ratio
    if ratio is None:
        return ComparisonRole.PRICE_ADJACENT.value
    if ratio < Decimal("0.92"):
        return ComparisonRole.DOWNTRADE_DIVERSION.value
    if ratio > Decimal("1.08"):
        return ComparisonRole.UPTRADE_ALTERNATIVE.value
    return ComparisonRole.PRICE_ADJACENT.value


def _primary_role(
    assembly: PairAnalysisAssembly,
    gate: PairGateEvaluation,
    questions: Sequence[str],
    roles: Sequence[str],
) -> str | None:
    if not roles:
        return None
    strength_by_question = {
        str(row.question_code): str(row.conclusion_strength)
        for row in gate.business_questions
    }
    ordered_questions = sorted(
        questions,
        key=lambda code: (
            -_STRENGTH_RANK[strength_by_question[code]],
            _QUESTION_PRIORITY_INDEX[code],
        ),
    )
    if ordered_questions:
        question = ordered_questions[0]
        role = (
            _price_ladder_role(assembly)
            if question == "price_ladder_defense"
            else _QUESTION_ROLE.get(question)
        )
        if role in roles:
            return role
    return roles[0]


def _select_priority_drafts(
    drafts: Sequence[_CandidateDraft],
) -> list[tuple[_CandidateDraft, str]]:
    remaining = [row for row in drafts if row.selection_eligible]
    remaining.sort(key=_base_order_key)
    if not remaining:
        return []
    first = remaining.pop(0)
    picks: list[tuple[_CandidateDraft, str]] = [(first, "highest_supported_priority")]
    covered_questions = {
        question
        for question in [_draft_primary_question(first)]
        if question is not None
    }
    covered_roles = {first.primary_role} if first.primary_role is not None else set()
    while remaining and len(picks) < MAX_PRIORITY_COMPETITORS:
        remaining.sort(
            key=lambda row: _diversity_order_key(
                row,
                covered_questions=covered_questions,
                covered_roles=covered_roles,
            )
        )
        chosen = remaining.pop(0)
        chosen_question = _draft_primary_question(chosen)
        adds_diversity = bool(
            chosen_question not in covered_questions
            or chosen.primary_role not in covered_roles
        )
        picks.append(
            (
                chosen,
                "adds_decision_role_coverage"
                if adds_diversity
                else "next_strongest_priority",
            )
        )
        if chosen_question is not None:
            covered_questions.add(chosen_question)
        if chosen.primary_role is not None:
            covered_roles.add(chosen.primary_role)
    return picks


def _draft_primary_question(draft: _CandidateDraft) -> str | None:
    if not draft.answerable_questions:
        return None
    strengths = {
        str(row.question_code): str(row.conclusion_strength)
        for row in draft.source.gate_evaluation.business_questions
    }
    return min(
        draft.answerable_questions,
        key=lambda code: (
            -_STRENGTH_RANK[strengths[code]],
            _QUESTION_PRIORITY_INDEX[code],
        ),
    )


def _base_order_key(draft: _CandidateDraft) -> tuple[object, ...]:
    score = (
        draft.score_breakdown.ranking_score
        if draft.score_breakdown and draft.score_breakdown.ranking_score is not None
        else Decimal("-1")
    )
    coverage = (
        draft.score_breakdown.available_weight
        if draft.score_breakdown
        else Decimal("0")
    )
    candidate = draft.source.gate_evaluation.candidate_sku_code or ""
    return (
        -_STRENGTH_RANK[draft.selection_strength],
        -score,
        -_STRENGTH_RANK[draft.market_strength],
        -coverage,
        draft.recall_rank or 10**9,
        _normalized_sku(candidate),
    )


def _diversity_order_key(
    draft: _CandidateDraft,
    *,
    covered_questions: set[str],
    covered_roles: set[str],
) -> tuple[object, ...]:
    primary_question = _draft_primary_question(draft)
    new_questions = (
        {primary_question}
        if primary_question is not None and primary_question not in covered_questions
        else set()
    )
    new_roles = (
        {draft.primary_role}
        if draft.primary_role is not None and draft.primary_role not in covered_roles
        else set()
    )
    question_strengths = {
        str(row.question_code): str(row.conclusion_strength)
        for row in draft.source.gate_evaluation.business_questions
    }
    new_strength = max(
        (_STRENGTH_RANK[question_strengths[code]] for code in new_questions),
        default=0,
    )
    return (
        -new_strength,
        -len(new_questions),
        -len(new_roles),
        *_base_order_key(draft),
    )


def _finalize_decision(
    draft: _CandidateDraft,
    *,
    picked: tuple[int, str] | None,
    covered_questions: set[str],
    covered_roles: set[str],
) -> PairSelectionDecision:
    gate = draft.source.gate_evaluation
    if picked is not None:
        rank, reason = picked
    elif gate.scope.scope_status == "excluded":
        rank = None
        reason = f"scope_excluded_{gate.scope.exclusion_reason_code}"
    elif not draft.selection_eligible:
        rank = None
        reason = "no_answerable_product_question"
    elif _draft_primary_question(draft) in covered_questions and (
        draft.primary_role in covered_roles
    ):
        rank = None
        reason = "stronger_candidate_covers_same_decision_role"
    else:
        rank = None
        reason = "priority_capacity_reached"
    reason_cn = (
        f"候选触发 {gate.scope.exclusion_reason_code}，不进入竞争排序。"
        if reason.startswith("scope_excluded_")
        else _SELECTION_REASON_CN[reason]
    )
    payload = {
        "project_id": gate.project_id,
        "category_code": str(gate.category_code),
        "competitor_profile_version_id": gate.competitor_profile_version_id,
        "release_scope_key": gate.release_scope_key,
        "target_sku_code": gate.target_sku_code,
        "candidate_sku_code": gate.candidate_sku_code,
        "scope_status": str(gate.scope.scope_status),
        "exclusion_reason_code": gate.scope.exclusion_reason_code,
        "score_breakdown": (
            draft.score_breakdown.model_dump(mode="json")
            if draft.score_breakdown
            else None
        ),
        "comparison_roles": list(draft.roles),
        "primary_role": draft.primary_role,
        "answerable_question_codes": list(draft.answerable_questions),
        "selection_conclusion_strength": draft.selection_strength,
        "selection_eligible": draft.selection_eligible,
        "selected": picked is not None,
        "selection_rank": rank,
        "selection_reason_code": reason,
        "selection_reason_cn": reason_cn,
        "market_validation_strength": draft.market_strength,
        "recall_rank": draft.recall_rank,
        "legacy_rank": draft.legacy_rank,
        "legacy_role": draft.legacy_role,
        "review_required": gate.review_required,
        "assembly_result_hash": (
            draft.source.assembly.result_hash if draft.source.assembly else None
        ),
        "gate_result_hash": gate.result_hash,
        "input_fingerprint": draft.input_fingerprint,
    }
    return PairSelectionDecision(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_v1_1_pair_selection_result_v1",
        ),
    )


def _priority_plans(
    decisions: Sequence[PairSelectionDecision],
) -> list[PrioritySelectionPlan]:
    selected = sorted(
        (row for row in decisions if row.selected),
        key=lambda row: row.selection_rank or 0,
    )
    result = []
    for row in selected:
        if (
            row.candidate_sku_code is None
            or row.selection_rank is None
            or row.primary_role is None
            or row.score_breakdown is None
        ):
            raise CompetitorSelectionInputError(
                "selected pair is missing identity, rank, role, or score process"
            )
        selection_score = row.score_breakdown.ranking_score or Decimal("0")
        payload = {
            "candidate_sku_code": row.candidate_sku_code,
            "selection_rank": row.selection_rank,
            "primary_role": str(row.primary_role),
            "role_codes": [str(item) for item in row.comparison_roles],
            "answerable_question_codes": row.answerable_question_codes,
            "selection_score": selection_score,
            "selection_available_weight": row.score_breakdown.available_weight,
            "selection_conclusion_strength": str(row.selection_conclusion_strength),
            "selection_reason_code": row.selection_reason_code,
            "selection_reason_cn": row.selection_reason_cn,
            "pair_selection_result_hash": row.result_hash,
        }
        result.append(
            PrioritySelectionPlan(
                **payload,
                result_hash=stable_hash(
                    payload,
                    version="competitor_profile_v1_1_priority_plan_result_v1",
                ),
            )
        )
    return result


def _role_buckets(
    decisions: Sequence[PairSelectionDecision],
) -> dict[str, list[str]]:
    result = {}
    for role in _ROLE_PRIORITY:
        codes = sorted(
            row.candidate_sku_code
            for row in decisions
            if row.candidate_sku_code
            and role in {str(item) for item in row.comparison_roles}
        )
        if codes:
            result[role] = codes
    return result


def _legacy_diffs(
    decisions: Sequence[PairSelectionDecision],
    legacy_top3: Sequence[LegacyTopCompetitorReference],
) -> list[LegacySelectionDiff]:
    decision_by_sku = {
        row.candidate_sku_code: row for row in decisions if row.candidate_sku_code
    }
    legacy_by_sku = {row.candidate_sku_code: row for row in legacy_top3}
    selected_by_sku = {row.candidate_sku_code: row for row in decisions if row.selected}
    result = []
    for sku in sorted(set(legacy_by_sku) | set(selected_by_sku)):
        old = legacy_by_sku.get(sku)
        new = selected_by_sku.get(sku)
        decision = decision_by_sku[sku]
        status = "retained" if old and new else "dropped" if old else "added"
        payload = {
            "candidate_sku_code": sku,
            "legacy_rank": old.legacy_rank if old else None,
            "new_rank": new.selection_rank if new else None,
            "diff_status": status,
            "reason_code": decision.selection_reason_code,
            "reason_cn": decision.selection_reason_cn,
        }
        result.append(LegacySelectionDiff(**payload))
    return result


def _assert_legacy_top3(rows: Sequence[LegacyTopCompetitorReference]) -> None:
    if len(rows) > MAX_PRIORITY_COMPETITORS:
        raise CompetitorSelectionInputError(
            "legacy Top 3 cannot contain more than three"
        )
    ranks = [row.legacy_rank for row in sorted(rows, key=lambda item: item.legacy_rank)]
    if ranks != list(range(1, len(ranks) + 1)):
        raise CompetitorSelectionInputError("legacy Top 3 ranks must be contiguous")
    codes = [row.candidate_sku_code for row in rows]
    if len(codes) != len(set(codes)):
        raise CompetitorSelectionInputError("legacy Top 3 candidates must be unique")


def _assert_selection_universe(
    rows: Sequence[PairSelectionInput],
    legacy_top3: Sequence[LegacyTopCompetitorReference],
) -> None:
    gates = [row.gate_evaluation for row in rows]
    scopes = {
        (
            row.project_id,
            str(row.category_code),
            row.competitor_profile_version_id,
            row.release_scope_key,
            row.target_sku_code,
        )
        for row in gates
    }
    if len(scopes) != 1:
        raise CompetitorSelectionInputError(
            "selection candidates must share one project/category/version/scope/target"
        )
    candidate_codes = [row.candidate_sku_code or "" for row in gates]
    if len(candidate_codes) != len(set(candidate_codes)):
        raise CompetitorSelectionInputError(
            "selection candidate universe must be unique"
        )
    available = set(candidate_codes)
    missing_legacy = sorted(
        row.candidate_sku_code
        for row in legacy_top3
        if row.candidate_sku_code not in available
    )
    if missing_legacy:
        raise CompetitorSelectionInputError(
            "legacy Top 3 must participate in the complete selection universe: "
            + ", ".join(missing_legacy)
        )
    legacy_by_sku = {row.candidate_sku_code: row for row in legacy_top3}
    for row in rows:
        code = row.gate_evaluation.candidate_sku_code or ""
        expected = legacy_by_sku.get(code)
        if expected is None:
            if row.legacy_rank is not None or row.legacy_role is not None:
                raise CompetitorSelectionInputError(
                    "pair legacy metadata must come from the frozen Top 3 reference"
                )
        elif (
            row.legacy_rank is not None and row.legacy_rank != expected.legacy_rank
        ) or (row.legacy_role is not None and row.legacy_role != expected.legacy_role):
            raise CompetitorSelectionInputError(
                "pair legacy metadata differs from the frozen Top 3 reference"
            )


def _assert_assembly_gate_authority(
    assembly: PairAnalysisAssembly,
    gate: PairGateEvaluation,
) -> None:
    if (
        assembly.project_id != gate.project_id
        or assembly.category_code != gate.category_code
        or assembly.competitor_profile_version_id != gate.competitor_profile_version_id
        or assembly.release_scope_key != gate.release_scope_key
        or assembly.target_sku_code != gate.target_sku_code
        or assembly.candidate_sku_code != gate.candidate_sku_code
        or assembly.target_snapshot_ref != gate.scope.target_snapshot_ref
        or assembly.candidate_snapshot_ref != gate.scope.candidate_snapshot_ref
    ):
        raise CompetitorSelectionInputError(
            "G33 assembly and G34 gate authority chains must match"
        )


def _assert_assembly_hash(assembly: PairAnalysisAssembly) -> None:
    expected = stable_hash(
        {
            "assembler_method_version": PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
            **assembly.model_dump(mode="json", exclude={"result_hash"}),
        },
        version=PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
    )
    if assembly.result_hash != expected:
        raise CompetitorSelectionInputError("G33 assembly result hash does not close")


def _assert_gate_hash(
    gate: PairGateEvaluation,
    *,
    assembly: PairAnalysisAssembly | None,
) -> None:
    _assert_scope_hash(gate.scope)
    if gate.scope.scope_status == "excluded":
        expected_input = stable_hash(
            {
                "scope_result_hash": gate.scope.result_hash,
                "method_version": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
                "config_version": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
            },
            version="competitor_profile_v1_1_excluded_gate_input_v1",
        )
        expected_result = stable_hash(
            {
                "input_fingerprint": expected_input,
                "scope_result_hash": gate.scope.result_hash,
            },
            version="competitor_profile_v1_1_excluded_gate_result_v1",
        )
    else:
        if assembly is None:
            raise CompetitorSelectionInputError(
                "analyzable G34 gates require their matching G33 assembly"
            )
        relation_hashes = {
            str(row.relation_code): gate.relation_source_hashes[str(row.relation_code)]
            for row in gate.relation_assessments
        }
        expected_input = stable_hash(
            {
                "scope_result_hash": gate.scope.result_hash,
                "assembly_result_hash": assembly.result_hash,
                "relation_source_hashes": relation_hashes,
                "relation_calculator_method_version": (
                    COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION
                ),
                "method_version": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
                "config_version": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
            },
            version="competitor_profile_v1_1_gate_input_v1",
        )
        expected_result = stable_hash(
            {
                "input_fingerprint": expected_input,
                "dimension_hashes": {
                    str(row.dimension_code): row.source_result_hash
                    for row in gate.dimension_states
                },
                "relation_hashes": {
                    str(row.relation_code): row.result_hash
                    for row in gate.relation_assessments
                },
                "question_hashes": {
                    str(row.question_code): row.result_hash
                    for row in gate.business_questions
                },
                "review_items": [
                    row.model_dump(mode="json") for row in gate.review_items
                ],
            },
            version="competitor_profile_v1_1_gate_result_v1",
        )
        supporting = {
            fact
            for row in gate.business_questions
            for fact in row.conclusion.supporting_fact_refs
        }
        dimension_hashes = {row.source_result_hash for row in gate.dimension_states}
        if not supporting.issubset(dimension_hashes):
            raise CompetitorSelectionInputError(
                "G34 question facts must reference its dimension states"
            )
    if gate.input_fingerprint != expected_input or gate.result_hash != expected_result:
        raise CompetitorSelectionInputError("G34 gate result hash does not close")


def _assert_scope_hash(scope: CandidateScopeAssessment) -> None:
    payload = {
        "project_id": scope.project_id,
        "category_code": str(scope.category_code),
        "competitor_profile_version_id": scope.competitor_profile_version_id,
        "release_scope_key": scope.release_scope_key,
        "target_sku_code": scope.target_sku_code,
        "candidate_sku_code": scope.candidate_sku_code,
        "target_snapshot_ref": scope.target_snapshot_ref,
        "candidate_snapshot_ref": scope.candidate_snapshot_ref,
        "scope_status": str(scope.scope_status),
        "exclusion_reason_code": scope.exclusion_reason_code,
        "review_items": [row.model_dump(mode="json") for row in scope.review_items],
        "input_fingerprint": scope.input_fingerprint,
    }
    expected = stable_hash(payload, version="competitor_profile_v1_1_scope_result_v1")
    if scope.result_hash != expected:
        raise CompetitorSelectionInputError("G34 candidate scope hash does not close")


def assert_pair_selection_integrity(
    decision: PairSelectionDecision,
    *,
    assembly: PairAnalysisAssembly | None,
    gate: PairGateEvaluation,
    verify_assembly_hash: bool = True,
) -> None:
    """Validate a frozen G33/G34/G35 chain without rerunning analysis."""

    if (
        decision.project_id != gate.project_id
        or decision.category_code != gate.category_code
        or decision.competitor_profile_version_id != gate.competitor_profile_version_id
        or decision.release_scope_key != gate.release_scope_key
        or decision.target_sku_code != gate.target_sku_code
        or decision.candidate_sku_code != gate.candidate_sku_code
        or decision.scope_status != gate.scope.scope_status
        or decision.exclusion_reason_code != gate.scope.exclusion_reason_code
        or decision.gate_result_hash != gate.result_hash
        or decision.assembly_result_hash
        != (assembly.result_hash if assembly is not None else None)
    ):
        raise CompetitorSelectionInputError(
            "G35 decision authority must match its G33/G34 source chain"
        )
    if assembly is not None:
        if verify_assembly_hash:
            _assert_assembly_hash(assembly)
        _assert_assembly_gate_authority(assembly, gate)
    _assert_gate_hash(gate, assembly=assembly)
    expected_decision_hash = stable_hash(
        decision.model_dump(mode="json", exclude={"result_hash"}),
        version="competitor_profile_v1_1_pair_selection_result_v1",
    )
    if decision.result_hash != expected_decision_hash:
        raise CompetitorSelectionInputError(
            "G35 pair decision result hash does not close"
        )


def assert_competitor_selection_result_integrity(
    result: CompetitorSelectionResult,
) -> None:
    """Validate G35 decision, priority, input, and result hashes only."""

    for plan in result.priority_competitors:
        expected_plan_hash = stable_hash(
            plan.model_dump(mode="python", exclude={"result_hash"}),
            version="competitor_profile_v1_1_priority_plan_result_v1",
        )
        if plan.result_hash != expected_plan_hash:
            raise CompetitorSelectionInputError(
                "G35 priority plan result hash does not close"
            )
    legacy_top3 = sorted(
        (
            {
                "candidate_sku_code": row.candidate_sku_code,
                "legacy_rank": row.legacy_rank,
                "legacy_role": row.legacy_role,
            }
            for row in result.pair_decisions
            if row.candidate_sku_code is not None and row.legacy_rank is not None
        ),
        key=lambda row: int(row["legacy_rank"] or 0),
    )
    expected_input = stable_hash(
        {
            "pair_input_hashes": {
                row.candidate_sku_code or "": row.input_fingerprint
                for row in result.pair_decisions
            },
            "legacy_top3": legacy_top3,
            "score_policy": result.score_policy.model_dump(mode="json"),
            "method_version": result.method_version,
            "config_version": result.config_version,
        },
        version="competitor_profile_v1_1_selection_input_v1",
    )
    expected_result = stable_hash(
        {
            "input_fingerprint": expected_input,
            "pair_decision_hashes": {
                row.candidate_sku_code or "": row.result_hash
                for row in result.pair_decisions
            },
            "priority_hashes": [row.result_hash for row in result.priority_competitors],
            "role_buckets": result.role_buckets,
            "legacy_selection_diffs": [
                row.model_dump(mode="json") for row in result.legacy_selection_diffs
            ],
        },
        version="competitor_profile_v1_1_selection_result_v1",
    )
    if (
        result.input_fingerprint != expected_input
        or result.result_hash != expected_result
    ):
        raise CompetitorSelectionInputError("G35 selection result hash does not close")


def _normalized_sku(value: str) -> str:
    return "".join(value.upper().split())


__all__ = [
    "COMPETITOR_PROFILE_V1_1_SELECTION_CONFIG_VERSION",
    "COMPETITOR_PROFILE_V1_1_SELECTION_METHOD_VERSION",
    "CompetitorProfileV11Selector",
    "CompetitorSelectionInputError",
    "CompetitorSelectionResult",
    "LegacySelectionDiff",
    "LegacyTopCompetitorReference",
    "MAX_PRIORITY_COMPETITORS",
    "PairSelectionDecision",
    "PairSelectionInput",
    "PrioritySelectionPlan",
    "assert_competitor_selection_result_integrity",
    "assert_pair_selection_integrity",
]
