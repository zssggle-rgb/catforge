"""Question-local table-stake and investment decisions for SPV V5.1.

Missing evidence produces a local no-conclusion state.  Only facts that are
directly used by the current question can create a review overlay, and that
overlay never escapes its target SKU, value bundle, and question.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CapabilityInvestmentInput,
    CapabilityThresholdConfig,
    InvestmentClassification,
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_threshold_config import (
    capability_threshold_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_thresholds import (
    compute_capability_prevalence,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    CapabilityInvestmentQuestionInput,
    InvestmentQuestionCode,
    InvestmentScopeReview,
    LocalCapabilityInvestmentDecision,
    QuestionConclusionStatus,
    TableStakeAssessment,
    TableStakeAssessmentStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_INVESTMENT_METHOD_VERSION = "sellpoint_value_local_investment_v5_1"
SPV_V5_1_LOCAL_REVIEW_METHOD_VERSION = "sellpoint_value_local_review_v5_1"

_INVESTMENT_DIMENSIONS = {
    "choice_support",
    "competitor_experience",
    "investment_level",
    "price_support",
    "relative_experience",
    "table_stake_assessment",
    "target_fact",
    "user_feedback",
    "volume_support",
}
_CONFIGURATION_DIMENSIONS = {
    "candidate_capability_facts",
    "current_competitive_performance",
    "target_fact",
}


def assess_capability_table_stake(
    item: CapabilityInvestmentInput,
    *,
    config: CapabilityThresholdConfig | None = None,
) -> TableStakeAssessment:
    """Map prevalence facts into a non-propagating V5.1 table-stake state."""

    config = config or capability_threshold_config(item.comparison_scope.category_code)
    prevalence = compute_capability_prevalence(
        candidate_facts=item.candidate_facts,
        comparison_scope=item.comparison_scope,
        config=config,
    )
    limitations: list[str] = []
    review_reasons: list[str] = []
    scope_complete = prevalence.threshold_status != "incomplete_scope"
    if prevalence.contradicted_count:
        status = TableStakeAssessmentStatus.INVALID
        review_reasons = ["candidate_fact_contradiction"]
    elif prevalence.threshold_status in {
        "insufficient_known_sample",
        "incomplete_scope",
    }:
        status = TableStakeAssessmentStatus.NOT_ASSESSED
        limitations = [
            "comparison_scope_incomplete"
            if prevalence.threshold_status == "incomplete_scope"
            else "threshold_known_sample_insufficient"
        ]
    elif prevalence.threshold_status == "meets_table_stake":
        status = TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE
    else:
        status = TableStakeAssessmentStatus.NOT_TABLE_STAKE
    exact_prevalence = (
        Decimal(prevalence.present_count) / Decimal(prevalence.known_count)
        if prevalence.known_count
        else None
    )
    return TableStakeAssessment(
        capability_code=item.capability_code,
        status=status,
        total_count=prevalence.total_candidate_count,
        known_count=prevalence.known_count,
        present_count=prevalence.present_count,
        absent_count=prevalence.absent_count,
        missing_count=prevalence.missing_count,
        contradicted_count=prevalence.contradicted_count,
        minimum_known_count=prevalence.minimum_known_count,
        prevalence_threshold=Decimal(str(prevalence.prevalence_threshold)),
        prevalence=exact_prevalence,
        scope_complete=scope_complete,
        exclude_from_core_sellpoints=(
            status == TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE
        ),
        limitations=limitations,
        review_required=bool(review_reasons),
        review_reasons=review_reasons,
    )


def classify_local_capability_investment(
    scoped: CapabilityInvestmentQuestionInput,
    *,
    config: CapabilityThresholdConfig | None = None,
) -> LocalCapabilityInvestmentDecision:
    """Classify one capability only inside one question/value/SKU scope."""

    scoped = CapabilityInvestmentQuestionInput.model_validate(
        scoped.model_dump(mode="python")
    )
    item = scoped.investment
    table_stake = assess_capability_table_stake(item, config=config)
    available = _available_dimensions(item, table_stake)
    relevant = (
        _INVESTMENT_DIMENSIONS
        if scoped.question_code == InvestmentQuestionCode.INVESTMENT_CONVERSION
        else _CONFIGURATION_DIMENSIONS
    )
    used: set[str] = set()
    direct_conflicts = _direct_conflicts(scoped.question_code, item)
    if direct_conflicts:
        classification: InvestmentClassification = "unknown"
        status = QuestionConclusionStatus.INVALID
        reason_cn = "当前问题直接使用的产品或用户事实存在冲突，暂不形成产品取舍结论。"
        confidence: Decimal | None = None
        review_reasons = direct_conflicts
    else:
        classification, reason_cn, confidence, used = _classify_question(
            scoped.question_code,
            item,
            table_stake,
        )
        status = (
            QuestionConclusionStatus.CONCLUSION_AVAILABLE
            if classification != "unknown"
            else QuestionConclusionStatus.NO_CONCLUSION
        )
        review_reasons = []
    unavailable = sorted(relevant - available)
    limitations = sorted(
        {
            *item.limitations,
            *(
                f"dimension_unavailable:{dimension}"
                for dimension in unavailable
                if status == QuestionConclusionStatus.NO_CONCLUSION
            ),
        }
    )
    evidence_refs = _evidence_refs(item)
    payload: dict[str, Any] = {
        "project_id": scoped.project_id,
        "category_code": scoped.category_code,
        "target_sku_code": scoped.target_sku_code,
        "question_code": scoped.question_code,
        "value_bundle_code": scoped.value_bundle_code,
        "capability_code": item.capability_code,
        "capability_name_cn": item.capability_name_cn,
        "classification": classification,
        "status": status,
        "table_stake_assessment": table_stake,
        "used_dimensions": sorted(used),
        "unavailable_dimensions": unavailable,
        "business_reason_cn": reason_cn,
        "confidence": confidence,
        "limitations": limitations,
        "review_required": bool(review_reasons),
        "review_reasons": review_reasons,
        "evidence_refs": evidence_refs,
    }
    return LocalCapabilityInvestmentDecision(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_INVESTMENT_METHOD_VERSION,
        ),
    )


def classify_local_capability_investments(
    items: Sequence[CapabilityInvestmentQuestionInput],
    *,
    configs: Mapping[str, CapabilityThresholdConfig] | None = None,
) -> list[LocalCapabilityInvestmentDecision]:
    """Classify scoped inputs deterministically without cross-scope propagation."""

    keys = [_input_key(row) for row in items]
    if len(keys) != len(set(keys)):
        raise ValueError("investment question inputs must be unique by local scope")
    return [
        classify_local_capability_investment(
            row,
            config=(configs or {}).get(row.category_code),
        )
        for row in sorted(items, key=_input_key)
    ]


def build_local_investment_review_overlays(
    decisions: Sequence[LocalCapabilityInvestmentDecision],
) -> list[InvestmentScopeReview]:
    """Aggregate review only within an identical question/value/SKU scope."""

    grouped: dict[
        tuple[str, str, str, str, str],
        list[LocalCapabilityInvestmentDecision],
    ] = defaultdict(list)
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for decision in decisions:
        key = (
            decision.project_id,
            decision.category_code,
            decision.target_sku_code,
            decision.question_code.value,
            decision.value_bundle_code,
            decision.capability_code,
        )
        if key in seen:
            raise ValueError("investment decisions must be unique by local scope")
        seen.add(key)
        grouped[key[:-1]].append(decision)
    result = []
    for scope_key in sorted(grouped):
        rows = grouped[scope_key]
        invalid = sorted(
            (row for row in rows if row.review_required),
            key=lambda row: row.capability_code,
        )
        reasons = sorted(
            {
                f"{row.capability_code}:{reason}"
                for row in invalid
                for reason in row.review_reasons
            }
        )
        evidence_refs = _dedupe_evidence_refs(
            [ref for row in invalid for ref in row.evidence_refs]
        )
        payload = {
            "project_id": scope_key[0],
            "category_code": scope_key[1],
            "target_sku_code": scope_key[2],
            "question_code": scope_key[3],
            "value_bundle_code": scope_key[4],
            "invalid_capability_codes": [row.capability_code for row in invalid],
            "review_required": bool(invalid),
            "review_reasons": reasons,
            "evidence_refs": evidence_refs,
        }
        result.append(
            InvestmentScopeReview(
                **payload,
                result_hash=stable_hash(
                    _json_payload(payload),
                    version=SPV_V5_1_LOCAL_REVIEW_METHOD_VERSION,
                ),
            )
        )
    return result


def _classify_question(
    question_code: InvestmentQuestionCode,
    item: CapabilityInvestmentInput,
    table_stake: TableStakeAssessment,
) -> tuple[InvestmentClassification, str, Decimal | None, set[str]]:
    if item.target_fact_status == "missing":
        return (
            "unknown",
            "本品是否具备这项能力尚无可靠事实，现有数据不足以形成产品取舍。",
            None,
            set(),
        )
    if question_code == InvestmentQuestionCode.INVESTMENT_CONVERSION:
        return _classify_conversion(item, table_stake)
    return _classify_configuration_follow(item, table_stake)


def _classify_conversion(
    item: CapabilityInvestmentInput,
    table_stake: TableStakeAssessment,
) -> tuple[InvestmentClassification, str, Decimal | None, set[str]]:
    if item.target_fact_status != "known_present":
        return (
            "unknown",
            "本品当前未确认具备这项能力，不在本项投入转化判断范围内。",
            None,
            {"target_fact"},
        )
    if (
        item.capability_kind == "capability"
        and table_stake.status == TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE
    ):
        return (
            "table_stake",
            "该能力已是当前市场基础能力，应保持可用性，但不承担核心卖点和溢价任务。",
            Decimal("0.85"),
            {"table_stake_assessment", "target_fact"},
        )
    market_supports = (item.price_support, item.volume_support, item.choice_support)
    supports_value = "positive" in market_supports and "negative" not in market_supports
    realized_advantage = (
        item.user_feedback_status in {"realized_advantage", "realized"}
        or (item.user_feedback_status == "partial" and item.investment_level == "high")
    ) and item.relative_experience_status == "advantage"
    if realized_advantage and supports_value:
        used = {
            "relative_experience",
            "target_fact",
            "user_feedback",
            *(
                dimension
                for dimension, status in (
                    ("price_support", item.price_support),
                    ("volume_support", item.volume_support),
                    ("choice_support", item.choice_support),
                )
                if status == "positive"
            ),
        }
        return (
            "retain",
            "这项投入已经形成用户可感知优势，并得到当前市场表现支持，下一代产品应继续保留。",
            Decimal("0.86"),
            used,
        )
    weak_realization = (
        item.user_feedback_status
        in {
            "partial",
            "not_observed",
            "weaker",
            "negative",
        }
        or item.relative_experience_status == "weaker"
    )
    material_investment = (
        item.investment_level == "high" or item.competitor_experience_stronger is True
    )
    if (
        item.capability_kind == "capability"
        and weak_realization
        and material_investment
    ):
        used = {"target_fact", "user_feedback"}
        if item.relative_experience_status != "unknown":
            used.add("relative_experience")
        if item.investment_level == "high":
            used.add("investment_level")
        if item.competitor_experience_stronger is not None:
            used.add("competitor_experience")
        return (
            "unconverted",
            "产品已经投入这项能力，但尚未转化成用户优势；应先解决体验兑现，不继续堆叠参数。",
            Decimal("0.80"),
            used,
        )
    return (
        "unknown",
        "现有产品事实、用户反馈和市场表现不足以判断这项投入应保留还是调整。",
        None,
        {"target_fact"},
    )


def _classify_configuration_follow(
    item: CapabilityInvestmentInput,
    table_stake: TableStakeAssessment,
) -> tuple[InvestmentClassification, str, Decimal | None, set[str]]:
    if item.target_fact_status != "known_absent":
        return (
            "unknown",
            "本品并非确认缺少这项能力，当前不形成是否跟进竞品配置的结论。",
            None,
            {"target_fact"} if item.target_fact_status != "missing" else set(),
        )
    if table_stake.present_count == 0:
        return (
            "unknown",
            "当前没有确认具备该能力的对照产品，无法判断是否需要跟进。",
            None,
            {"target_fact"},
        )
    if item.current_competitive_performance in {"stronger", "not_weaker"}:
        return (
            "do_not_follow",
            "本品未配置这项能力，但当前竞争表现没有因此受损，现阶段无需为了参数对齐而跟进。",
            Decimal("0.82"),
            {
                "candidate_capability_facts",
                "current_competitive_performance",
                "target_fact",
            },
        )
    if item.current_competitive_performance == "weaker":
        return (
            "missing_competitive_gap",
            "本品缺少这项能力，且具备该能力的对照产品当前表现更好，应进入产品定义缺口评估。",
            Decimal("0.84"),
            {
                "candidate_capability_facts",
                "current_competitive_performance",
                "target_fact",
            },
        )
    return (
        "unknown",
        "当前胜负表现不足，暂不能判断这项竞品配置是否需要跟进。",
        None,
        {"candidate_capability_facts", "target_fact"},
    )


def _available_dimensions(
    item: CapabilityInvestmentInput,
    table_stake: TableStakeAssessment,
) -> set[str]:
    result: set[str] = set()
    if item.target_fact_status in {"known_present", "known_absent"}:
        result.add("target_fact")
    if item.investment_level != "unknown":
        result.add("investment_level")
    if item.user_feedback_status not in {"unknown", "conflicted"}:
        result.add("user_feedback")
    if item.relative_experience_status not in {"unknown", "conflicted"}:
        result.add("relative_experience")
    if item.competitor_experience_stronger is not None:
        result.add("competitor_experience")
    for dimension, status in (
        ("price_support", item.price_support),
        ("volume_support", item.volume_support),
        ("choice_support", item.choice_support),
    ):
        if status != "unknown":
            result.add(dimension)
    if item.current_competitive_performance not in {"unknown", "conflicted"}:
        result.add("current_competitive_performance")
    if table_stake.present_count:
        result.add("candidate_capability_facts")
    if table_stake.status in {
        TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE,
        TableStakeAssessmentStatus.NOT_TABLE_STAKE,
    }:
        result.add("table_stake_assessment")
    return result


def _direct_conflicts(
    question_code: InvestmentQuestionCode,
    item: CapabilityInvestmentInput,
) -> list[str]:
    reasons = []
    if item.target_fact_status == "contradicted":
        reasons.append("target_fact_contradicted")
    if question_code == InvestmentQuestionCode.INVESTMENT_CONVERSION:
        if item.user_feedback_status == "conflicted":
            reasons.append("user_feedback_conflicted")
        if item.relative_experience_status == "conflicted":
            reasons.append("relative_experience_conflicted")
    else:
        if any(fact.fact_status == "contradicted" for fact in item.candidate_facts):
            reasons.append("candidate_fact_contradiction")
        if item.current_competitive_performance == "conflicted":
            reasons.append("current_competitive_performance_conflicted")
    return sorted(reasons)


def _evidence_refs(item: CapabilityInvestmentInput) -> list[SellpointValueEvidenceRef]:
    return _dedupe_evidence_refs(
        [
            *item.evidence_refs,
            *(ref for fact in item.candidate_facts for ref in fact.evidence_refs),
        ]
    )


def _dedupe_evidence_refs(
    rows: Sequence[SellpointValueEvidenceRef],
) -> list[SellpointValueEvidenceRef]:
    by_key = {
        (
            row.module_code,
            row.record_type,
            row.record_id,
            row.result_hash,
        ): row
        for row in rows
    }
    return [by_key[key] for key in sorted(by_key)]


def _input_key(
    row: CapabilityInvestmentQuestionInput,
) -> tuple[str, str, str, str, str, str]:
    return (
        row.project_id,
        row.category_code,
        row.target_sku_code,
        row.question_code.value,
        row.value_bundle_code,
        row.investment.capability_code,
    )


def _json_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else [
                row.model_dump(mode="json") if hasattr(row, "model_dump") else row
                for row in value
            ]
            if isinstance(value, list)
            else value.value
            if hasattr(value, "value")
            else value
        )
        for key, value in payload.items()
    }


__all__ = [
    "SPV_V5_1_INVESTMENT_METHOD_VERSION",
    "SPV_V5_1_LOCAL_REVIEW_METHOD_VERSION",
    "assess_capability_table_stake",
    "build_local_investment_review_overlays",
    "classify_local_capability_investment",
    "classify_local_capability_investments",
]
