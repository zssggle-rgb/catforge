"""Deterministic capability prevalence and product-investment decisions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CapabilityCandidateFact,
    CapabilityComparisonScope,
    CapabilityInvestmentDecision,
    CapabilityInvestmentInput,
    CapabilityPrevalenceSummary,
    CapabilityThresholdConfig,
    InvestmentClassification,
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_threshold_config import (
    capability_threshold_config,
)
from app.services.core3_real_data.hash_utils import stable_hash


THRESHOLD_HASH_VERSION = "sellpoint_value_capability_threshold_v1"
DECISION_HASH_VERSION = "sellpoint_value_investment_decision_v1"


def compute_capability_prevalence(
    *,
    candidate_facts: Sequence[CapabilityCandidateFact],
    comparison_scope: CapabilityComparisonScope,
    config: CapabilityThresholdConfig,
) -> CapabilityPrevalenceSummary:
    """Count known facts only; missing and contradictions never become absent."""

    if comparison_scope.category_code != config.category_code:
        raise ValueError("comparison scope and threshold category must match")
    ordered = sorted(candidate_facts, key=lambda row: row.candidate_sku_code)
    codes = [row.candidate_sku_code for row in ordered]
    if len(codes) != len(set(codes)):
        raise ValueError("candidate facts must be unique by sku_code")
    if not set(codes).issubset(set(comparison_scope.candidate_scope_ids)):
        raise ValueError("candidate facts must belong to the comparison scope")
    normalized_scope = comparison_scope.model_copy(
        update={
            "battlefield_codes": sorted(set(comparison_scope.battlefield_codes)),
            "competitor_roles": sorted(set(comparison_scope.competitor_roles)),
            "candidate_scope_ids": sorted(set(comparison_scope.candidate_scope_ids)),
        }
    )

    present_count = sum(row.fact_status == "known_present" for row in ordered)
    absent_count = sum(row.fact_status == "known_absent" for row in ordered)
    missing_count = sum(row.fact_status == "missing" for row in ordered)
    contradicted_count = sum(row.fact_status == "contradicted" for row in ordered)
    known_count = present_count + absent_count
    prevalence = (
        float(Decimal(present_count) / Decimal(known_count))
        if known_count
        else None
    )
    incomplete_dimensions = _incomplete_scope_dimensions(normalized_scope, config)
    if incomplete_dimensions:
        threshold_status = "incomplete_scope"
    elif known_count < config.minimum_known_count:
        threshold_status = "insufficient_known_sample"
    elif prevalence is not None and prevalence >= config.prevalence_threshold:
        threshold_status = "meets_table_stake"
    else:
        threshold_status = "below_table_stake"

    fact_payload = [row.model_dump(mode="json") for row in ordered]
    return CapabilityPrevalenceSummary(
        config_version=config.config_version,
        config_validation_status=config.validation_status,
        total_candidate_count=len(ordered),
        known_count=known_count,
        present_count=present_count,
        absent_count=absent_count,
        missing_count=missing_count,
        contradicted_count=contradicted_count,
        prevalence=prevalence,
        threshold_status=threshold_status,
        minimum_known_count=config.minimum_known_count,
        prevalence_threshold=config.prevalence_threshold,
        comparison_scope=normalized_scope,
        candidate_fact_hash=stable_hash(
            {
                "facts": fact_payload,
                "scope_hash": normalized_scope.scope_hash,
                "config": config.model_dump(mode="json"),
            },
            version=THRESHOLD_HASH_VERSION,
        ),
    )


def classify_capability_investment(
    item: CapabilityInvestmentInput,
    *,
    config: CapabilityThresholdConfig | None = None,
) -> CapabilityInvestmentDecision:
    """Translate facts into one PM action while preserving review boundaries."""

    config = config or capability_threshold_config(item.comparison_scope.category_code)
    prevalence = compute_capability_prevalence(
        candidate_facts=item.candidate_facts,
        comparison_scope=item.comparison_scope,
        config=config,
    )
    classification, reason_cn, confidence, decision_reasons = _classify(
        item,
        prevalence,
    )
    review_reasons = _dedupe(
        [
            *decision_reasons,
            *(
                ["candidate_fact_contradiction"]
                if prevalence.contradicted_count
                else []
            ),
            *(
                ["comparison_scope_incomplete"]
                if prevalence.threshold_status == "incomplete_scope"
                else []
            ),
            *(
                ["threshold_known_sample_insufficient"]
                if prevalence.threshold_status == "insufficient_known_sample"
                else []
            ),
            *item.limitations,
        ]
    )
    if classification == "unknown" and "decision_not_identified" not in review_reasons:
        review_reasons.append("decision_not_identified")
        review_reasons.sort()
    review_status = (
        "review_required" if review_reasons or classification == "unknown" else "auto_pass"
    )
    evidence_refs = _evidence_refs(item)
    boundary_cn = _boundary_cn(item, prevalence, config, review_reasons)
    payload: dict[str, Any] = {
        "capability_code": item.capability_code,
        "capability_name_cn": item.capability_name_cn,
        "capability_kind": item.capability_kind,
        "parent_capability_code": item.parent_capability_code,
        "classification": classification,
        "target_fact_status": item.target_fact_status,
        "target_value": item.target_value,
        "investment_level": item.investment_level,
        "prevalence_summary": prevalence,
        "user_feedback_status": item.user_feedback_status,
        "relative_experience_status": item.relative_experience_status,
        "competitor_experience_stronger": item.competitor_experience_stronger,
        "price_support": item.price_support,
        "volume_support": item.volume_support,
        "choice_support": item.choice_support,
        "current_competitive_performance": item.current_competitive_performance,
        "experience_outcomes": sorted(set(item.experience_outcomes)),
        "candidate_scope_ids": sorted(item.comparison_scope.candidate_scope_ids),
        "business_reason_cn": reason_cn,
        "boundary_cn": boundary_cn,
        "confidence": confidence,
        "review_status": review_status,
        "review_reasons": review_reasons,
        "evidence_refs": evidence_refs,
    }
    hash_payload = {
        key: (
            value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else [row.model_dump(mode="json") for row in value]
            if key == "evidence_refs"
            else value
        )
        for key, value in payload.items()
    }
    return CapabilityInvestmentDecision(
        **payload,
        decision_hash=stable_hash(hash_payload, version=DECISION_HASH_VERSION),
    )


def classify_capability_investments(
    items: Sequence[CapabilityInvestmentInput],
    *,
    configs: Mapping[str, CapabilityThresholdConfig] | None = None,
) -> list[CapabilityInvestmentDecision]:
    """Classify a batch in deterministic capability order."""

    codes = [item.capability_code for item in items]
    if len(codes) != len(set(codes)):
        raise ValueError("capability inputs must be unique by capability_code")
    result = []
    for item in sorted(items, key=lambda row: row.capability_code):
        category_code = item.comparison_scope.category_code
        config = (configs or {}).get(category_code)
        result.append(classify_capability_investment(item, config=config))
    return result


def _classify(
    item: CapabilityInvestmentInput,
    prevalence: CapabilityPrevalenceSummary,
) -> tuple[InvestmentClassification, str, float, list[str]]:
    if item.target_fact_status == "contradicted":
        return (
            "unknown",
            "目标产品是否具备这项能力存在事实冲突，暂不进入产品取舍结论。",
            0.2,
            ["target_fact_contradicted"],
        )
    if item.target_fact_status == "missing":
        return (
            "unknown",
            "目标产品是否具备这项能力尚无可靠事实，不能按缺失配置处理。",
            0.2,
            ["target_fact_missing"],
        )
    if (
        item.capability_kind == "capability"
        and item.target_fact_status == "known_present"
        and prevalence.threshold_status == "meets_table_stake"
    ):
        return (
            "table_stake",
            "该能力在当前竞争范围内已是普遍配置，产品需要保持，但不应再把它作为核心溢价理由。",
            _table_stake_confidence(prevalence),
            [],
        )

    signal_conflict = (
        item.user_feedback_status == "conflicted"
        or item.relative_experience_status == "conflicted"
        or item.current_competitive_performance == "conflicted"
    )
    if signal_conflict:
        return (
            "unknown",
            "用户体验或当前竞争表现存在冲突，暂不能据此决定保留、跟进或补齐。",
            0.3,
            ["decision_signal_conflicted"],
        )

    if item.target_fact_status == "known_present":
        market_supports = (
            item.price_support,
            item.volume_support,
            item.choice_support,
        )
        supports_value = "positive" in market_supports and "negative" not in market_supports
        realized_advantage = (
            (
                item.user_feedback_status in {"realized_advantage", "realized"}
                or (
                    item.user_feedback_status == "partial"
                    and item.investment_level == "high"
                )
            )
            and item.relative_experience_status == "advantage"
        )
        if realized_advantage and supports_value:
            return (
                "retain",
                "这项投入已经形成用户可感知优势，并得到当前量价或选择表现支持，后续产品定义应继续保留。",
                _retain_confidence(market_supports),
                [],
            )
        weak_realization = (
            item.user_feedback_status
            in {"partial", "not_observed", "weaker", "negative"}
            or item.relative_experience_status == "weaker"
        )
        material_investment = (
            item.investment_level == "high"
            or item.competitor_experience_stronger is True
        )
        if item.capability_kind == "capability" and weak_realization and material_investment:
            return (
                "unconverted",
                "产品已经投入这项能力，但用户体验尚未形成或弱于对照产品；应先解决体验兑现，不建议继续堆参数。",
                0.84 if item.competitor_experience_stronger else 0.78,
                [],
            )
        return (
            "unknown",
            "产品已具备这项能力，但现有用户体验和市场表现不足以判断应保留还是调整。",
            0.4,
            ["present_capability_decision_evidence_insufficient"],
        )

    present_comparators = prevalence.present_count > 0
    if item.target_fact_status == "known_absent" and present_comparators:
        if item.current_competitive_performance in {"stronger", "not_weaker"}:
            return (
                "do_not_follow",
                "对照产品具备这项能力，但本品未配置仍未在当前竞争中吃亏，现阶段无需为了对齐参数而跟进。",
                0.86
                if item.current_competitive_performance == "stronger"
                else 0.8,
                [],
            )
        if item.current_competitive_performance == "weaker":
            return (
                "missing_competitive_gap",
                "本品缺少这项能力，具备该能力的对照产品当前表现更好，已构成需要优先评估的产品定义缺口。",
                0.86,
                [],
            )
    return (
        "unknown",
        "现有竞品事实或当前胜负不足，暂不能判断这项能力是否需要跟进。",
        0.35,
        ["absent_capability_competitive_effect_unknown"],
    )


def _incomplete_scope_dimensions(
    scope: CapabilityComparisonScope,
    config: CapabilityThresholdConfig,
) -> list[str]:
    return [
        dimension
        for dimension in config.required_scope_dimensions
        if not getattr(scope, dimension, None)
    ]


def _table_stake_confidence(prevalence: CapabilityPrevalenceSummary) -> float:
    sample_bonus = min(prevalence.known_count, 20) / 100
    prevalence_margin = max(
        (prevalence.prevalence or 0.0) - prevalence.prevalence_threshold,
        0.0,
    )
    return min(round(0.75 + sample_bonus + prevalence_margin * 0.1, 4), 0.99)


def _retain_confidence(supports: Sequence[str]) -> float:
    positive_count = sum(status == "positive" for status in supports)
    return min(0.82 + positive_count * 0.04, 0.94)


def _boundary_cn(
    item: CapabilityInvestmentInput,
    prevalence: CapabilityPrevalenceSummary,
    config: CapabilityThresholdConfig,
    review_reasons: Sequence[str],
) -> str:
    prevalence_text = (
        f"{prevalence.prevalence:.1%}"
        if prevalence.prevalence is not None
        else "不可计算"
    )
    parts = [
        f"当前范围共 {prevalence.total_candidate_count} 个候选，"
        f"其中 {prevalence.known_count} 个能力事实已知、"
        f"{prevalence.missing_count} 个缺失、"
        f"{prevalence.contradicted_count} 个冲突；"
        f"已知样本具备率为 {prevalence_text}。",
        f"门槛暂按 {config.minimum_known_count} 个已知样本、"
        f"{config.prevalence_threshold:.0%} 普及率判断。",
    ]
    if item.capability_kind == "capability":
        parts.append("门槛判断只作用于配置能力，关联的用户体验结果仍需单独比较。")
    if review_reasons:
        parts.append(f"当前仍需复核：{', '.join(review_reasons)}。")
    return "".join(parts)


def _evidence_refs(
    item: CapabilityInvestmentInput,
) -> list[SellpointValueEvidenceRef]:
    rows = [
        *item.evidence_refs,
        *(ref for fact in item.candidate_facts for ref in fact.evidence_refs),
    ]
    by_key = {
        (row.module_code, row.record_type, row.record_id, row.result_hash): row
        for row in rows
    }
    return [by_key[key] for key in sorted(by_key)]


def _dedupe(values: Sequence[str]) -> list[str]:
    return sorted({value for value in values if value})


__all__ = [
    "DECISION_HASH_VERSION",
    "THRESHOLD_HASH_VERSION",
    "classify_capability_investment",
    "classify_capability_investments",
    "compute_capability_prevalence",
]
