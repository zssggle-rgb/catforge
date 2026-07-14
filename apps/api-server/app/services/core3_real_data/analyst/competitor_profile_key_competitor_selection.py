"""Select the smallest zero-to-three set that adds verified decision information."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection_schemas import (
    DecisionTopicAssessment,
    KeyCompetitorPairSelectionDecision,
    KeyCompetitorSelectionBundle,
    KeyCompetitorSelectionConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationEvaluationBundle,
    CompetitorRelationPairEvaluation,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceRef,
    KeyCompetitorSelectionDraft,
    QuestionEligibility,
    RelationAssessment,
)
from app.services.core3_real_data.hash_utils import stable_hash


_TOPIC_QUESTIONS = {
    "purchase_choice": ("purchase_choice",),
    "price_scale_pressure": ("price_volume_pressure", "price_ladder_defense"),
    "portfolio_or_scenario": (
        "same_brand_portfolio_role",
        "scenario_solution",
    ),
    "value_route": ("value_substitution",),
}
_SPECIALIZED_QUESTIONS = {"configuration_follow"}
_F1_F4 = {"F1_purchase_reason", "F4_user_realization"}
_PRESSURE_CLARITY_RANK = {"none": 0, "limited": 1, "clear": 2, "strong": 3}
_STATUS_RANK = {"limited": 1, "passed": 2}
_CONFIDENCE_RANK = {"medium": 1, "high": 2}
_REASON_CN = {
    "ineligible_status": "该产品当前仅是召回或分析参照，尚未形成可进入重点名单的正式竞争关系。",
    "review_required": "该产品的关键证据仍需复核，暂不进入重点竞品名单。",
    "question_unavailable": "现有关系和证据还不足以支持把该产品列为重点竞品。",
    "confidence_insufficient": "该产品虽有候选关系，但证据置信度不足以驱动重点决策。",
    "no_verified_decision_topic": "该产品尚未回答购买选择、量价压力、产品线场景或价值路线中的任何重点问题。",
    "topic_already_covered": "该产品提供的决策信息已由已入选产品覆盖，无需重复占用重点位置。",
    "weaker_duplicate_pressure": "该产品形成的是相同类型压力，但关系完整度或证据强度弱于已入选产品。",
    "specialized_question_only": "该产品仅适合配置等专项问答，尚不足以进入综合重点竞品名单。",
    "selection_capacity_reached": "已有三款产品覆盖更优先的独立决策问题，本产品保留在完整候选中供专项查看。",
}
_SELECTION_REASON_CN = {
    "purchase_choice": "它与本品形成已验证的直接或同预算选择关系，是判断用户会在哪两款之间取舍的首要参照。",
    "price_scale_pressure": "它在价格梯度或市场承接上形成已验证压力，直接影响本品的价格与规模防守。",
    "portfolio_or_scenario": "它揭示了同品牌产品线重叠或另一种场景方案，影响本品的产品角色定义。",
    "value_route": "它证明同一用户价值可以被替代或由另一条价值路线实现，影响卖点投入与强化方向。",
}
_SELECTION_REASON_CN_BY_RELATION = {
    "same_brand_ladder": "它揭示了同品牌产品线的升降档关系，影响本品的产品角色定义。",
    "scenario_substitute": "它提供了满足同一场景的另一种产品方案，影响本品的目标用户和使用场景定位。",
}
_INDEPENDENT_REASON_CN = {
    "purchase_choice": "它补充回答了谁最可能与本品进入同一购买选择；同主题其他候选没有提供更强且更完整的证据。",
    "price_scale_pressure": "它补充回答了本品在上探、下探或同预算竞争中应重点防守谁；同主题其他候选没有形成更明确的市场压力。",
    "portfolio_or_scenario": "它补充回答了产品线内部角色或同场景替代方案是否构成压力；其他候选没有新增这一决策信息。",
    "value_route": "它补充回答了哪条用户价值路线最容易替代本品；同主题其他候选的关系或证据完整度更弱。",
}


class KeyCompetitorSelectionError(RuntimeError):
    """Raised when a relation bundle and selection config cannot be combined."""


@dataclass(frozen=True)
class _CandidateAnalysis:
    pair: CompetitorRelationPairEvaluation
    topics: dict[str, DecisionTopicAssessment]
    selection_eligible: bool
    gate_reason_code: str | None


@dataclass(frozen=True)
class _SelectionPick:
    analysis: _CandidateAnalysis
    primary_topic: str
    rank: int


class KeyCompetitorSelector:
    """Choose a deterministic minimal decision set without a cross-topic score."""

    def select(
        self,
        relation_bundle: CompetitorRelationEvaluationBundle,
        config: KeyCompetitorSelectionConfig,
    ) -> KeyCompetitorSelectionBundle:
        if config.product_category != relation_bundle.product_category:
            raise KeyCompetitorSelectionError(
                "selection config category must match relation bundle"
            )
        analyses = [
            _analyze_candidate(pair, config)
            for pair in sorted(
                relation_bundle.pairs,
                key=lambda row: _normalized_sku(row.candidate.sku_code),
            )
        ]
        picks = _select_minimal_set(analyses, config)
        selections = [
            _selection_draft(pick, relation_bundle.target.sku_code, config)
            for pick in picks
        ]
        pair_decisions = [
            _pair_decision(analysis, picks, config) for analysis in analyses
        ]
        covered = [
            topic
            for topic in config.decision_topic_order
            if any(
                decision.selected and topic in decision.covered_decision_topics
                for decision in pair_decisions
            )
        ]
        uncovered = [
            topic for topic in config.decision_topic_order if topic not in covered
        ]
        selection_state = _selection_state(analyses, picks)
        limitations = _bundle_limitations(selection_state, uncovered)
        input_fingerprint = stable_hash(
            {
                "relation_evaluation_result_hash": relation_bundle.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_key_selection_input_v1",
        )
        return KeyCompetitorSelectionBundle(
            project_id=relation_bundle.project_id,
            category_code=relation_bundle.category_code,
            product_category=relation_bundle.product_category,
            release_scope_key=relation_bundle.release_scope_key,
            target=relation_bundle.target,
            candidate_count=len(pair_decisions),
            pair_decisions=pair_decisions,
            selected_count=len(selections),
            selections=selections,
            selection_state=selection_state,
            covered_decision_topics=covered,
            uncovered_decision_topics=uncovered,
            review_required=selection_state == "review_required",
            limitations=limitations,
            config=config,
            relation_evaluation_result_hash=relation_bundle.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "input_fingerprint": input_fingerprint,
                    "pair_decision_hashes": {
                        row.candidate.sku_code: row.result_hash
                        for row in pair_decisions
                    },
                    "selection_hashes": [row.result_hash for row in selections],
                    "selection_state": selection_state,
                    "covered_decision_topics": covered,
                    "uncovered_decision_topics": uncovered,
                    "limitations": limitations,
                },
                version="competitor_profile_key_selection_result_v1",
            ),
        )


def _analyze_candidate(
    pair: CompetitorRelationPairEvaluation,
    config: KeyCompetitorSelectionConfig,
) -> _CandidateAnalysis:
    topics = {
        topic: _topic_assessment(pair, topic, config)
        for topic in config.decision_topic_order
    }
    gate_reason = _candidate_gate_reason(pair, topics)
    return _CandidateAnalysis(
        pair=pair,
        topics=topics,
        selection_eligible=gate_reason is None,
        gate_reason_code=gate_reason,
    )


def _topic_assessment(
    pair: CompetitorRelationPairEvaluation,
    topic: str,
    config: KeyCompetitorSelectionConfig,
) -> DecisionTopicAssessment:
    question_rows = [_question(pair, code) for code in _TOPIC_QUESTIONS[topic]]
    question_eligible = any(row.availability == "eligible" for row in question_rows)
    relevant_codes = config.topic_relation_priority[topic]
    formal_relations = [
        _relation(pair, code)
        for code in relevant_codes
        if _relation(pair, code).status in {"passed", "limited"}
        and _relation(pair, code).confidence_level in {"high", "medium"}
    ]
    formal_relations.sort(key=lambda row: _relation_order_key(row, relevant_codes))
    eligible = question_eligible and bool(formal_relations)
    best = formal_relations[0] if eligible else None
    pressure_clarity = _market_pressure_clarity(pair, question_rows, formal_relations)
    reason_code = (
        "verified_decision_topic"
        if eligible
        else "topic_question_unavailable"
        if not question_eligible
        else "topic_relation_unavailable"
    )
    evidence_refs = _merge_refs(*(row.evidence_refs for row in formal_relations))
    payload = {
        "topic_code": topic,
        "eligible": eligible,
        "usable_relation_codes": [
            _enum_value(row.relation_code) for row in formal_relations
        ],
        "best_relation_code": _enum_value(best.relation_code) if best else None,
        "best_relation_status": _enum_value(best.status) if best else None,
        "best_confidence_level": (_enum_value(best.confidence_level) if best else None),
        "independent_evidence_family_count": (
            len(best.supporting_evidence_families) if best else 0
        ),
        "f1_f4_evidence_count": (
            len(
                {_enum_value(code) for code in best.supporting_evidence_families}
                & _F1_F4
            )
            if best
            else 0
        ),
        "market_pressure_clarity": pressure_clarity,
        "limitation_count": (
            len(set(pair.limitations) | set(best.limitations)) if best else 0
        ),
        "reason_code": reason_code,
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
    }
    return DecisionTopicAssessment(
        topic_code=topic,
        eligible=eligible,
        usable_relation_codes=payload["usable_relation_codes"],
        best_relation_code=payload["best_relation_code"],
        best_relation_status=payload["best_relation_status"],
        best_confidence_level=payload["best_confidence_level"],
        independent_evidence_family_count=payload["independent_evidence_family_count"],
        f1_f4_evidence_count=payload["f1_f4_evidence_count"],
        market_pressure_clarity=pressure_clarity,
        limitation_count=payload["limitation_count"],
        reason_code=reason_code,
        evidence_refs=evidence_refs,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_decision_topic_assessment_v1",
        ),
    )


def _candidate_gate_reason(
    pair: CompetitorRelationPairEvaluation,
    topics: dict[str, DecisionTopicAssessment],
) -> str | None:
    if pair.review_required or pair.candidate_status == "review_required":
        return "review_required"
    if pair.candidate_status not in {"eligible", "limited"}:
        return "ineligible_status"
    key_question = _question(pair, "key_competitor_selection")
    if key_question.availability != "eligible":
        return "question_unavailable"
    formal = [
        row for row in pair.relation_assessments if row.status in {"passed", "limited"}
    ]
    if not any(row.confidence_level in {"high", "medium"} for row in formal):
        return "confidence_insufficient"
    if not any(row.eligible for row in topics.values()):
        return (
            "specialized_question_only"
            if any(
                _question(pair, code).availability == "eligible"
                for code in _SPECIALIZED_QUESTIONS
            )
            else "no_verified_decision_topic"
        )
    return None


def _select_minimal_set(
    analyses: Sequence[_CandidateAnalysis],
    config: KeyCompetitorSelectionConfig,
) -> list[_SelectionPick]:
    picks: list[_SelectionPick] = []
    selected_codes: set[str] = set()
    for topic in config.decision_topic_order:
        if len(picks) >= config.max_selected_count:
            break
        candidates = [
            row
            for row in analyses
            if row.selection_eligible
            and row.pair.candidate.sku_code not in selected_codes
            and row.topics[topic].eligible
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda row: _candidate_topic_order_key(row, topic))
        best = candidates[0]
        current = [
            pick.analysis for pick in picks if pick.analysis.topics[topic].eligible
        ]
        if current:
            current.sort(key=lambda row: _candidate_topic_order_key(row, topic))
            if not _meaningfully_stronger(
                best.topics[topic],
                current[0].topics[topic],
                topic,
            ):
                continue
        pick = _SelectionPick(
            analysis=best,
            primary_topic=topic,
            rank=len(picks) + 1,
        )
        picks.append(pick)
        selected_codes.add(best.pair.candidate.sku_code)
    return picks


def _meaningfully_stronger(
    candidate: DecisionTopicAssessment,
    incumbent: DecisionTopicAssessment,
    topic: str,
) -> bool:
    candidate_status = _STATUS_RANK[_enum_value(candidate.best_relation_status)]
    incumbent_status = _STATUS_RANK[_enum_value(incumbent.best_relation_status)]
    if candidate_status != incumbent_status:
        return candidate_status > incumbent_status
    candidate_confidence = _CONFIDENCE_RANK[
        _enum_value(candidate.best_confidence_level)
    ]
    incumbent_confidence = _CONFIDENCE_RANK[
        _enum_value(incumbent.best_confidence_level)
    ]
    if candidate_confidence != incumbent_confidence:
        return candidate_confidence > incumbent_confidence
    if (
        candidate.independent_evidence_family_count
        > incumbent.independent_evidence_family_count
        and candidate.f1_f4_evidence_count >= incumbent.f1_f4_evidence_count
    ):
        return True
    if topic == "price_scale_pressure" and (
        _PRESSURE_CLARITY_RANK[candidate.market_pressure_clarity]
        > _PRESSURE_CLARITY_RANK[incumbent.market_pressure_clarity]
        and candidate.f1_f4_evidence_count >= incumbent.f1_f4_evidence_count
    ):
        return True
    return False


def _selection_draft(
    pick: _SelectionPick,
    target_sku_code: str,
    config: KeyCompetitorSelectionConfig,
) -> KeyCompetitorSelectionDraft:
    pair = pick.analysis.pair
    primary = pick.analysis.topics[pick.primary_topic]
    covered_topics = [
        topic
        for topic in config.decision_topic_order
        if pick.analysis.topics[topic].eligible
    ]
    formal_relations = [
        row
        for row in pair.relation_assessments
        if row.status in {"passed", "limited"}
        and row.confidence_level in {"high", "medium"}
    ]
    primary_relation = _enum_value(primary.best_relation_code)
    auxiliary = sorted(
        {
            _enum_value(row.relation_code)
            for row in formal_relations
            if _enum_value(row.relation_code) != primary_relation
        }
    )
    evidence_refs = _merge_refs(*(row.evidence_refs for row in formal_relations))
    summary = {
        "candidate_status": pair.candidate_status,
        "primary_decision_topic": pick.primary_topic,
        "relation_statuses": {
            _enum_value(row.relation_code): _enum_value(row.status)
            for row in formal_relations
        },
        "business_effects": {
            _enum_value(row.relation_code): row.business_effect
            for row in formal_relations
            if row.business_effect
        },
        "available_evidence_families": sorted(
            {
                _enum_value(code)
                for row in formal_relations
                for code in row.supporting_evidence_families
            }
        ),
        "market_pressure_clarity": primary.market_pressure_clarity,
    }
    payload = {
        "target_sku_code": target_sku_code,
        "candidate_sku_code": pair.candidate.sku_code,
        "selection_rank": pick.rank,
        "primary_decision_topic": pick.primary_topic,
        "covered_decision_topics": covered_topics,
        "primary_relation_code": primary_relation,
        "auxiliary_relation_codes": auxiliary,
        "selection_reason_cn": _selection_reason_cn(
            pick.primary_topic,
            primary_relation,
        ),
        "independent_information_reason_cn": _INDEPENDENT_REASON_CN[pick.primary_topic],
        "price_value_pressure_summary": summary,
        "confidence_level": primary.best_confidence_level,
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
    }
    return KeyCompetitorSelectionDraft(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_key_competitor_selection_v1",
        ),
    )


def _selection_reason_cn(primary_topic: str, primary_relation: str) -> str:
    if primary_topic == "portfolio_or_scenario":
        return _SELECTION_REASON_CN_BY_RELATION.get(
            primary_relation,
            _SELECTION_REASON_CN[primary_topic],
        )
    return _SELECTION_REASON_CN[primary_topic]


def _pair_decision(
    analysis: _CandidateAnalysis,
    picks: Sequence[_SelectionPick],
    config: KeyCompetitorSelectionConfig,
) -> KeyCompetitorPairSelectionDecision:
    pair = analysis.pair
    selected_pick = next(
        (
            pick
            for pick in picks
            if pick.analysis.pair.candidate.sku_code == pair.candidate.sku_code
        ),
        None,
    )
    if selected_pick:
        covered = [
            topic
            for topic in config.decision_topic_order
            if analysis.topics[topic].eligible
        ]
        reason_code = None
        reason_cn = None
    else:
        covered = []
        reason_code = analysis.gate_reason_code or _eligible_non_selection_reason(
            analysis,
            picks,
            config,
        )
        reason_cn = _REASON_CN[reason_code]
    input_fingerprint = stable_hash(
        {
            "relation_evaluation_pair_result_hash": pair.result_hash,
            "topic_hashes": {
                topic: analysis.topics[topic].result_hash
                for topic in config.decision_topic_order
            },
            "selected": selected_pick is not None,
            "selection_rank": selected_pick.rank if selected_pick else None,
            "primary_decision_topic": (
                selected_pick.primary_topic if selected_pick else None
            ),
            "non_selection_reason_code": reason_code,
            "config_version": config.config_version,
        },
        version="competitor_profile_pair_selection_input_v1",
    )
    payload = {
        "target_sku_code": pair.target.sku_code,
        "candidate_sku_code": pair.candidate.sku_code,
        "source_candidate_status": pair.candidate_status,
        "selection_eligible": analysis.selection_eligible,
        "topic_hashes": [
            analysis.topics[topic].result_hash for topic in config.decision_topic_order
        ],
        "selected": selected_pick is not None,
        "selection_rank": selected_pick.rank if selected_pick else None,
        "primary_decision_topic": (
            selected_pick.primary_topic if selected_pick else None
        ),
        "covered_decision_topics": covered,
        "non_selection_reason_code": reason_code,
        "non_selection_reason_cn": reason_cn,
        "relation_evaluation_pair_result_hash": pair.result_hash,
        "config_version": config.config_version,
        "input_fingerprint": input_fingerprint,
    }
    return KeyCompetitorPairSelectionDecision(
        target=pair.target,
        candidate=pair.candidate,
        source_candidate_status=pair.candidate_status,
        selection_eligible=analysis.selection_eligible,
        topic_assessments=[
            analysis.topics[topic] for topic in config.decision_topic_order
        ],
        selected=selected_pick is not None,
        selection_rank=selected_pick.rank if selected_pick else None,
        primary_decision_topic=(selected_pick.primary_topic if selected_pick else None),
        covered_decision_topics=covered,
        non_selection_reason_code=reason_code,
        non_selection_reason_cn=reason_cn,
        evidence_refs=pair.evidence_refs,
        relation_evaluation_pair_result_hash=pair.result_hash,
        config_version=config.config_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_pair_selection_result_v1",
        ),
    )


def _eligible_non_selection_reason(
    analysis: _CandidateAnalysis,
    picks: Sequence[_SelectionPick],
    config: KeyCompetitorSelectionConfig,
) -> str:
    eligible_topics = [
        topic
        for topic in config.decision_topic_order
        if analysis.topics[topic].eligible
    ]
    covered = {
        topic
        for pick in picks
        for topic in config.decision_topic_order
        if pick.analysis.topics[topic].eligible
    }
    if any(topic not in covered for topic in eligible_topics):
        return "selection_capacity_reached"
    for topic in eligible_topics:
        incumbents = [
            pick.analysis for pick in picks if pick.analysis.topics[topic].eligible
        ]
        if not incumbents:
            continue
        incumbents.sort(key=lambda row: _candidate_topic_order_key(row, topic))
        if _topic_strength_key(incumbents[0].topics[topic]) > _topic_strength_key(
            analysis.topics[topic]
        ):
            return "weaker_duplicate_pressure"
    return "topic_already_covered"


def _selection_state(
    analyses: Sequence[_CandidateAnalysis],
    picks: Sequence[_SelectionPick],
) -> str:
    if picks:
        return "selected"
    if any(
        row.pair.review_required
        or row.pair.candidate_status in {"review_required", "blocked"}
        for row in analyses
    ):
        return "review_required"
    if any(
        relation.status == "unassessable"
        for row in analyses
        for relation in row.pair.relation_assessments
    ):
        return "insufficient_evidence"
    return "no_priority_competitor"


def _bundle_limitations(selection_state: str, uncovered: Sequence[str]) -> list[str]:
    result = []
    if uncovered:
        result.append("not_all_decision_topics_have_verified_key_competitors")
    if selection_state == "insufficient_evidence":
        result.append("candidate_relations_contain_unassessable_required_facts")
    if selection_state == "review_required":
        result.append("candidate_evidence_requires_review_before_key_selection")
    return sorted(result)


def _candidate_topic_order_key(
    analysis: _CandidateAnalysis,
    topic: str,
) -> tuple[int, int, int, int, int, int, str]:
    row = analysis.topics[topic]
    return (
        -_STATUS_RANK[_enum_value(row.best_relation_status)],
        -_CONFIDENCE_RANK[_enum_value(row.best_confidence_level)],
        -row.independent_evidence_family_count,
        -row.f1_f4_evidence_count,
        -_PRESSURE_CLARITY_RANK[row.market_pressure_clarity],
        row.limitation_count,
        _normalized_sku(analysis.pair.candidate.sku_code),
    )


def _topic_strength_key(
    row: DecisionTopicAssessment,
) -> tuple[int, int, int, int, int, int]:
    return (
        _STATUS_RANK[_enum_value(row.best_relation_status)],
        _CONFIDENCE_RANK[_enum_value(row.best_confidence_level)],
        row.independent_evidence_family_count,
        row.f1_f4_evidence_count,
        _PRESSURE_CLARITY_RANK[row.market_pressure_clarity],
        -row.limitation_count,
    )


def _relation_order_key(
    row: RelationAssessment,
    priority: Sequence[str],
) -> tuple[int, int, int, int, int, int, int]:
    families = {_enum_value(code) for code in row.supporting_evidence_families}
    return (
        -_STATUS_RANK[_enum_value(row.status)],
        -_CONFIDENCE_RANK[_enum_value(row.confidence_level)],
        -len(families),
        -len(families & _F1_F4),
        -int(bool(row.business_effect.get("strong_pressure"))),
        len(row.limitations),
        priority.index(_enum_value(row.relation_code)),
    )


def _market_pressure_clarity(
    pair: CompetitorRelationPairEvaluation,
    topic_questions: Sequence[QuestionEligibility],
    relations: Sequence[RelationAssessment],
) -> str:
    if any(bool(row.business_effect.get("strong_pressure")) for row in relations):
        return "strong"
    pressure_question = _question(pair, "price_volume_pressure")
    if pressure_question.availability == "eligible" and relations:
        return "clear"
    if pressure_question.availability == "limited" or any(
        row.availability == "limited" for row in topic_questions
    ):
        return "limited"
    return "none"


def _question(
    pair: CompetitorRelationPairEvaluation,
    code: str,
) -> QuestionEligibility:
    return next(row for row in pair.question_eligibility if row.question_code == code)


def _relation(
    pair: CompetitorRelationPairEvaluation,
    code: str,
) -> RelationAssessment:
    return next(row for row in pair.relation_assessments if row.relation_code == code)


def _normalized_sku(value: str) -> str:
    return "".join(value.upper().split())


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _merge_refs(*groups: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {}
    for group in groups:
        for ref in group:
            key = (
                ref.module_code,
                ref.source_batch_id or "",
                ref.record_type,
                ref.record_id,
                ref.result_hash,
            )
            by_key[key] = ref
    return [by_key[key] for key in sorted(by_key)]


__all__ = ["KeyCompetitorSelectionError", "KeyCompetitorSelector"]
