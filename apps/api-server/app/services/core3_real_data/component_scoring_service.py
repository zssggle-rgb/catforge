"""M13 component scoring service.

M13 consumes the M12 candidate pair and feature snapshot. It does not read raw
source tables, does not recall new candidates, and does not select final Core3
competitors.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.component_scoring_repositories import (
    ComponentScoringRepository,
    M13CandidateInput,
    M13InputBlockedError,
)
from app.services.core3_real_data.component_scoring_schemas import (
    M13BuildArtifacts,
    M13CandidateComponentExplanationRecord,
    M13CandidateComponentScoreRecord,
    M13CandidateRoleScoreRecord,
    M13CandidateScoreReviewIssueRecord,
    M13ServiceResult,
)
from app.services.core3_real_data.constants import (
    CORE3_M13_COMPONENT_RULE_VERSION,
    CORE3_M13_ROLE_RULE_VERSION,
    CORE3_M13_RULE_VERSION,
    Core3RunStatus,
    M13ComponentCode,
    M13IssueLevel,
    M13IssueScope,
    M13ReviewIssueType,
    M13RoleCode,
    M13SampleStatus,
    M13SupportLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash


BOUNDARY_NOTE_CN = "M13 只对 M12 候选做组件评分、角色评分和证据解释，不选择核心三竞品、不生成高层报告。"

COMPONENT_LABEL_CN: dict[M13ComponentCode, str] = {
    M13ComponentCode.BASE_COMPARABILITY: "同场可比基础",
    M13ComponentCode.BATTLEFIELD_FIT: "价值战场重合",
    M13ComponentCode.TASK_OVERLAP: "用户任务重合",
    M13ComponentCode.AUDIENCE_OVERLAP: "目标客群重合",
    M13ComponentCode.PRICE_POSITION: "价位接近度",
    M13ComponentCode.PRICE_ADVANTAGE: "价格拦截力度",
    M13ComponentCode.SIZE_FIT: "尺寸形态匹配",
    M13ComponentCode.CHANNEL_OVERLAP: "渠道平台重合",
    M13ComponentCode.PARAM_SIMILARITY: "参数相似度",
    M13ComponentCode.PARAM_SUPERIORITY: "参数优势压力",
    M13ComponentCode.CLAIM_CONFRONTATION: "卖点价值对打",
    M13ComponentCode.CLAIM_SUPERIORITY: "卖点优势压力",
    M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY: "门槛卖点满足",
    M13ComponentCode.MARKET_THREAT: "市场压力",
    M13ComponentCode.SALES_AMOUNT_STRENGTH: "销额强度",
    M13ComponentCode.COMMENT_PERCEPTION: "评论感知支撑",
    M13ComponentCode.PRICE_TREND: "价格趋势压力",
    M13ComponentCode.EVIDENCE_COMPLETENESS: "证据完整度",
}

ROLE_LABEL_CN: dict[M13RoleCode, str] = {
    M13RoleCode.DIRECT_FIGHT: "正面对打",
    M13RoleCode.PRICE_VOLUME_PRESSURE: "价格销量挤压",
    M13RoleCode.BENCHMARK_POTENTIAL: "高端标杆/潜在下探",
    M13RoleCode.CONFIGURATION_PRESSURE: "配置拦截",
    M13RoleCode.SERVICE_REFERENCE: "服务参照",
}

COMPONENT_WEIGHTS: dict[M13ComponentCode, Decimal] = {
    M13ComponentCode.BASE_COMPARABILITY: Decimal("0.10"),
    M13ComponentCode.BATTLEFIELD_FIT: Decimal("0.12"),
    M13ComponentCode.TASK_OVERLAP: Decimal("0.08"),
    M13ComponentCode.AUDIENCE_OVERLAP: Decimal("0.07"),
    M13ComponentCode.PRICE_POSITION: Decimal("0.06"),
    M13ComponentCode.PRICE_ADVANTAGE: Decimal("0.04"),
    M13ComponentCode.SIZE_FIT: Decimal("0.04"),
    M13ComponentCode.CHANNEL_OVERLAP: Decimal("0.05"),
    M13ComponentCode.PARAM_SIMILARITY: Decimal("0.06"),
    M13ComponentCode.PARAM_SUPERIORITY: Decimal("0.04"),
    M13ComponentCode.CLAIM_CONFRONTATION: Decimal("0.10"),
    M13ComponentCode.CLAIM_SUPERIORITY: Decimal("0.05"),
    M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY: Decimal("0.04"),
    M13ComponentCode.MARKET_THREAT: Decimal("0.08"),
    M13ComponentCode.SALES_AMOUNT_STRENGTH: Decimal("0.04"),
    M13ComponentCode.COMMENT_PERCEPTION: Decimal("0.03"),
    M13ComponentCode.PRICE_TREND: Decimal("0.03"),
    M13ComponentCode.EVIDENCE_COMPLETENESS: Decimal("0.02"),
}

ROLE_COMPONENT_WEIGHTS: dict[M13RoleCode, dict[M13ComponentCode, Decimal]] = {
    M13RoleCode.DIRECT_FIGHT: {
        M13ComponentCode.BASE_COMPARABILITY: Decimal("0.16"),
        M13ComponentCode.BATTLEFIELD_FIT: Decimal("0.20"),
        M13ComponentCode.TASK_OVERLAP: Decimal("0.12"),
        M13ComponentCode.AUDIENCE_OVERLAP: Decimal("0.10"),
        M13ComponentCode.PRICE_POSITION: Decimal("0.12"),
        M13ComponentCode.CHANNEL_OVERLAP: Decimal("0.08"),
        M13ComponentCode.PARAM_SIMILARITY: Decimal("0.10"),
        M13ComponentCode.CLAIM_CONFRONTATION: Decimal("0.12"),
    },
    M13RoleCode.PRICE_VOLUME_PRESSURE: {
        M13ComponentCode.PRICE_ADVANTAGE: Decimal("0.22"),
        M13ComponentCode.MARKET_THREAT: Decimal("0.22"),
        M13ComponentCode.SALES_AMOUNT_STRENGTH: Decimal("0.16"),
        M13ComponentCode.CHANNEL_OVERLAP: Decimal("0.12"),
        M13ComponentCode.BASE_COMPARABILITY: Decimal("0.12"),
        M13ComponentCode.PRICE_TREND: Decimal("0.10"),
        M13ComponentCode.EVIDENCE_COMPLETENESS: Decimal("0.06"),
    },
    M13RoleCode.BENCHMARK_POTENTIAL: {
        M13ComponentCode.CLAIM_SUPERIORITY: Decimal("0.18"),
        M13ComponentCode.PARAM_SUPERIORITY: Decimal("0.18"),
        M13ComponentCode.BATTLEFIELD_FIT: Decimal("0.16"),
        M13ComponentCode.MARKET_THREAT: Decimal("0.14"),
        M13ComponentCode.PRICE_POSITION: Decimal("0.12"),
        M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY: Decimal("0.12"),
        M13ComponentCode.EVIDENCE_COMPLETENESS: Decimal("0.10"),
    },
    M13RoleCode.CONFIGURATION_PRESSURE: {
        M13ComponentCode.PARAM_SUPERIORITY: Decimal("0.24"),
        M13ComponentCode.CLAIM_SUPERIORITY: Decimal("0.18"),
        M13ComponentCode.SIZE_FIT: Decimal("0.14"),
        M13ComponentCode.PRICE_POSITION: Decimal("0.12"),
        M13ComponentCode.CLAIM_CONFRONTATION: Decimal("0.12"),
        M13ComponentCode.BASE_COMPARABILITY: Decimal("0.10"),
        M13ComponentCode.EVIDENCE_COMPLETENESS: Decimal("0.10"),
    },
    M13RoleCode.SERVICE_REFERENCE: {
        M13ComponentCode.COMMENT_PERCEPTION: Decimal("0.24"),
        M13ComponentCode.BATTLEFIELD_FIT: Decimal("0.18"),
        M13ComponentCode.EVIDENCE_COMPLETENESS: Decimal("0.18"),
        M13ComponentCode.AUDIENCE_OVERLAP: Decimal("0.14"),
        M13ComponentCode.TASK_OVERLAP: Decimal("0.12"),
        M13ComponentCode.BASE_COMPARABILITY: Decimal("0.08"),
        M13ComponentCode.CHANNEL_OVERLAP: Decimal("0.06"),
    },
}


@dataclass(frozen=True)
class _ComponentDraft:
    code: M13ComponentCode
    score: Decimal
    confidence: Decimal
    support_level: M13SupportLevel
    summary_cn: str
    positive_summary_cn: str | None
    gap_summary_cn: str | None
    source_payload: dict[str, Any]
    evidence_ids: tuple[str, ...]
    missing_reasons: tuple[dict[str, Any] | str, ...] = ()
    risk_flags: tuple[dict[str, Any] | str, ...] = ()
    weakening_evidence_ids: tuple[str, ...] = ()


class ComponentScoringService:
    def __init__(self, repository: ComponentScoringRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M13_RULE_VERSION,
        max_pairs: int | None = None,
        resume_unscored_only: bool = True,
    ) -> M13ServiceResult:
        total_pair_count = self.repository.count_current_candidate_pairs(batch_id, sku_scope=sku_scope)
        scored_pair_count_before = self.repository.count_current_component_scores(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
        )
        pending_pair_count_before = max(total_pair_count - scored_pair_count_before, 0)
        items = self.repository.list_current_candidate_inputs(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
            max_pairs=max_pairs,
            only_unscored=resume_unscored_only,
        )
        if not items:
            if total_pair_count == 0:
                raise M13InputBlockedError("M13 没有可评分的 M12 当前候选 pair。")
            scored_pair_count_after = self.repository.count_current_component_scores(
                batch_id,
                sku_scope=sku_scope,
                rule_version=rule_version,
            )
            return M13ServiceResult(
                status=Core3RunStatus.SUCCESS,
                input_count=0,
                output_count=0,
                created_output_count=0,
                warnings=[],
                component_scores=[],
                role_scores=[],
                explanations=[],
                review_issues=[],
                summary={
                    "module_code": "M13",
                    "batch_id": batch_id,
                    "target_sku_count": 0,
                    "candidate_pair_count": 0,
                    "component_score_count": 0,
                    "role_score_count": 0,
                    "component_explanation_count": 0,
                    "review_issue_count": 0,
                    "review_required_pair_count": 0,
                    "total_candidate_pair_count": total_pair_count,
                    "scored_pair_count_before": scored_pair_count_before,
                    "pending_pair_count_before": pending_pair_count_before,
                    "scored_pair_count_after": scored_pair_count_after,
                    "pending_pair_count_after": max(total_pair_count - scored_pair_count_after, 0),
                    "max_pairs": max_pairs,
                    "resume_unscored_only": resume_unscored_only,
                    "batch_limited": False,
                    "batch_completed": True,
                    "boundary_note": BOUNDARY_NOTE_CN,
                    "source_modules": ["M12"],
                },
            )

        artifacts: list[M13BuildArtifacts] = []
        blocked_issues: list[M13CandidateScoreReviewIssueRecord] = []
        for item in items:
            if item.snapshot is None:
                blocked_issues.append(
                    _issue_record(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        item=item,
                        component_score_id=None,
                        issue_type=M13ReviewIssueType.MISSING_FEATURE_SNAPSHOT.value,
                        issue_level=M13IssueLevel.BLOCKER,
                        issue_scope=M13IssueScope.PAIR,
                        message_cn="该候选缺少 M12 pair 特征快照，M13 不能重新回读原始表补评分。",
                        suggested_action_cn="先重跑 M12 候选召回，生成 feature snapshot 后再进入 M13。",
                    )
                )
                continue
            artifacts.append(self._build_pair_artifacts(batch_id, run_id, module_run_id, rule_version, item))

        component_records = [artifact.component_score for artifact in artifacts]
        role_records = [role for artifact in artifacts for role in artifact.role_scores]
        explanation_records = [explanation for artifact in artifacts for explanation in artifact.explanations]
        review_issue_records = [issue for artifact in artifacts for issue in artifact.review_issues] + blocked_issues

        component_result = self.repository.save_component_scores(component_records)
        role_result = self.repository.save_role_scores(role_records)
        explanation_result = self.repository.save_explanations(explanation_records)
        issue_result = self.repository.save_review_issues(review_issue_records)
        scored_pair_count_after = self.repository.count_current_component_scores(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
        )
        pending_pair_count_after = max(total_pair_count - scored_pair_count_after, 0)

        review_required_count = sum(1 for record in component_records if record.review_required) + len(blocked_issues)
        warnings = []
        if review_required_count:
            warnings.append(f"M13 有 {review_required_count} 个候选评分需要复核，不能直接进入自动核心竞品选择。")
        if blocked_issues:
            warnings.append(f"M13 有 {len(blocked_issues)} 个候选缺少 M12 快照，已阻断评分。")
        if pending_pair_count_after > 0:
            warnings.append(
                f"M13 本次处理 {len(items)} 个候选 pair，仍有 {pending_pair_count_after} 个待评分；请继续执行 M13 直到待评分为 0。"
            )

        created_output_count = (
            component_result.created_count
            + role_result.created_count
            + explanation_result.created_count
            + issue_result.created_count
        )
        output_count = len(component_records) + len(role_records) + len(explanation_records) + len(review_issue_records)
        status = Core3RunStatus.SUCCESS
        if blocked_issues:
            status = Core3RunStatus.WARNING
        elif review_required_count:
            status = Core3RunStatus.WARNING
        if pending_pair_count_after > 0:
            status = Core3RunStatus.WARNING

        target_count = len({record.target_sku_code for record in component_records})
        summary = {
            "module_code": "M13",
            "batch_id": batch_id,
            "target_sku_count": target_count,
            "candidate_pair_count": len(component_records),
            "component_score_count": len(component_records),
            "role_score_count": len(role_records),
            "component_explanation_count": len(explanation_records),
            "review_issue_count": len(review_issue_records),
            "review_required_pair_count": review_required_count,
            "total_candidate_pair_count": total_pair_count,
            "scored_pair_count_before": scored_pair_count_before,
            "pending_pair_count_before": pending_pair_count_before,
            "processed_pair_count": len(items),
            "scored_pair_count_after": scored_pair_count_after,
            "pending_pair_count_after": pending_pair_count_after,
            "max_pairs": max_pairs,
            "resume_unscored_only": resume_unscored_only,
            "batch_limited": pending_pair_count_after > 0,
            "batch_completed": pending_pair_count_after == 0,
            "boundary_note": BOUNDARY_NOTE_CN,
            "source_modules": ["M12"],
            "downstream_usage": {
                "M14": "读取组件总分、三类核心角色分、置信度、复核状态做三槽位选择。",
                "M15": "读取组件解释和 evidence 生成业务证据卡。",
                "M16": "读取评分复核问题进入人工复核队列。",
            },
            "created_counts": {
                "component_scores": component_result.created_count,
                "role_scores": role_result.created_count,
                "explanations": explanation_result.created_count,
                "review_issues": issue_result.created_count,
            },
            "reused_counts": {
                "component_scores": component_result.reused_count,
                "role_scores": role_result.reused_count,
                "explanations": explanation_result.reused_count,
                "review_issues": issue_result.reused_count,
            },
        }
        return M13ServiceResult(
            status=status,
            input_count=len(items),
            output_count=output_count,
            created_output_count=created_output_count,
            warnings=warnings,
            component_scores=component_records,
            role_scores=role_records,
            explanations=explanation_records,
            review_issues=review_issue_records,
            summary=summary,
        )

    def _build_pair_artifacts(
        self,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        item: M13CandidateInput,
    ) -> M13BuildArtifacts:
        pool = item.pool
        snapshot = item.snapshot
        if snapshot is None:
            raise M13InputBlockedError("M13 component scoring requires feature snapshot")
        components = _build_components(item)
        role_scores = _build_role_scores(components, item)
        total_score = _weighted_score({code: draft.score for code, draft in components.items()}, COMPONENT_WEIGHTS)
        evidence_ids = _unique_evidence_ids([pool.evidence_ids or (), snapshot.evidence_ids or (), *(reason.evidence_ids or () for reason in item.reasons)])
        positive_evidence_ids = _unique_evidence_ids(draft.evidence_ids for draft in components.values())
        weakening_evidence_ids = _unique_evidence_ids(draft.weakening_evidence_ids for draft in components.values())
        confidence = _pair_confidence(components, pool)
        review_required, review_reason = _component_review_state(components, role_scores, pool, confidence)
        component_score_id = _record_id(
            "m13score",
            batch_id,
            pool.target_sku_code,
            pool.candidate_sku_code,
            rule_version,
            snapshot.feature_snapshot_hash,
        )
        input_payload = {
            "candidate_pool_id": pool.candidate_pool_id,
            "feature_snapshot_id": snapshot.candidate_feature_snapshot_id,
            "feature_snapshot_hash": snapshot.feature_snapshot_hash,
            "rule_version": rule_version,
        }
        component_payload = _component_payload_json(components, role_scores)
        component_score = M13CandidateComponentScoreRecord(
            candidate_component_score_id=component_score_id,
            candidate_pool_id=pool.candidate_pool_id,
            feature_snapshot_id=snapshot.candidate_feature_snapshot_id,
            project_id=pool.project_id,
            category_code=pool.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=pool.target_sku_code,
            target_model_name=pool.target_model_name,
            candidate_sku_code=pool.candidate_sku_code,
            candidate_model_name=pool.candidate_model_name,
            candidate_brand_name=pool.candidate_brand_name,
            same_brand_flag=bool(pool.same_brand_flag),
            candidate_relation_types_json=list(pool.relation_types_json or ()),
            candidate_role_hints_json=list(pool.role_hints_json or ()),
            recall_strength=str(pool.recall_strength),
            base_comparability_score=components[M13ComponentCode.BASE_COMPARABILITY].score,
            battlefield_fit_score=components[M13ComponentCode.BATTLEFIELD_FIT].score,
            task_overlap_score=components[M13ComponentCode.TASK_OVERLAP].score,
            audience_overlap_score=components[M13ComponentCode.AUDIENCE_OVERLAP].score,
            price_position_score=components[M13ComponentCode.PRICE_POSITION].score,
            price_advantage_score=components[M13ComponentCode.PRICE_ADVANTAGE].score,
            size_fit_score=components[M13ComponentCode.SIZE_FIT].score,
            channel_overlap_score=components[M13ComponentCode.CHANNEL_OVERLAP].score,
            param_similarity_score=components[M13ComponentCode.PARAM_SIMILARITY].score,
            param_superiority_score=components[M13ComponentCode.PARAM_SUPERIORITY].score,
            claim_confrontation_score=components[M13ComponentCode.CLAIM_CONFRONTATION].score,
            claim_superiority_score=components[M13ComponentCode.CLAIM_SUPERIORITY].score,
            claim_threshold_sufficiency_score=components[M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY].score,
            market_threat_score=components[M13ComponentCode.MARKET_THREAT].score,
            sales_amount_strength_score=components[M13ComponentCode.SALES_AMOUNT_STRENGTH].score,
            comment_perception_score=components[M13ComponentCode.COMMENT_PERCEPTION].score,
            price_trend_score=components[M13ComponentCode.PRICE_TREND].score,
            evidence_completeness_score=components[M13ComponentCode.EVIDENCE_COMPLETENESS].score,
            component_scores_json=component_payload,
            component_total_score=total_score,
            direct_fight_score=role_scores[M13RoleCode.DIRECT_FIGHT],
            price_volume_pressure_score=role_scores[M13RoleCode.PRICE_VOLUME_PRESSURE],
            benchmark_potential_score=role_scores[M13RoleCode.BENCHMARK_POTENTIAL],
            configuration_pressure_score=role_scores[M13RoleCode.CONFIGURATION_PRESSURE],
            service_reference_score=role_scores[M13RoleCode.SERVICE_REFERENCE],
            confidence=confidence,
            sample_status=_sample_status(pool),
            main_strengths_json=_main_strengths(components),
            main_gaps_json=_main_gaps(components),
            risk_flags_json=_pair_risk_flags(components, pool, role_scores),
            review_required=review_required,
            review_reason=review_reason,
            positive_evidence_ids=positive_evidence_ids,
            weakening_evidence_ids=weakening_evidence_ids,
            evidence_ids=evidence_ids,
            target_profile_hash=pool.target_profile_hash,
            candidate_profile_hash=pool.candidate_profile_hash,
            feature_snapshot_hash=snapshot.feature_snapshot_hash,
            component_rule_version=CORE3_M13_COMPONENT_RULE_VERSION,
            role_rule_version=CORE3_M13_ROLE_RULE_VERSION,
            rule_version=rule_version,
            input_fingerprint=stable_hash(input_payload, version="m13_component_input_v1"),
            result_hash=stable_hash(
                {
                    **input_payload,
                    "component_scores": component_payload,
                    "total_score": total_score,
                    "role_scores": role_scores,
                    "confidence": confidence,
                },
                version="m13_component_result_v1",
            ),
            processing_status="warning" if review_required else "success",
            review_status="review_required" if review_required else "auto_pass",
            review_reason_json={"review_reason": review_reason} if review_required else {},
        )
        role_records = tuple(
            _role_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                role_code=role_code,
                role_score=score,
                components=components,
                pair_confidence=confidence,
            )
            for role_code, score in role_scores.items()
        )
        explanations = tuple(
            _explanation_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                component=draft,
            )
            for draft in components.values()
        )
        review_issues = tuple(
            _review_issues(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                components=components,
                role_scores=role_scores,
                pair_confidence=confidence,
                total_score=total_score,
            )
        )
        return M13BuildArtifacts(
            component_score=component_score,
            role_scores=role_records,
            explanations=explanations,
            review_issues=review_issues,
        )


def _build_components(item: M13CandidateInput) -> dict[M13ComponentCode, _ComponentDraft]:
    pool = item.pool
    snapshot = item.snapshot
    source = _snapshot_source(snapshot)
    battlefield = _dict(source.get("battlefield_overlap"))
    task = _dict(source.get("task_overlap"))
    audience = _dict(source.get("audience_overlap"))
    claim = _dict(source.get("claim_value_overlap"))
    price = _dict(source.get("price_feature") or _dict(source.get("market_feature")).get("price"))
    market = _dict(source.get("market_feature"))
    channel = _dict(source.get("channel_feature"))
    param = _dict(source.get("param_feature"))
    quality = _dict(source.get("quality_feature"))

    size_score = _size_score(str(pool.size_relation), param)
    price_position_score = _price_position_score(str(pool.price_relation), price)
    channel_score = _channel_score(channel)
    param_similarity = _param_similarity_score(param)
    claim_confrontation = _overlap_score(claim)
    battlefield_score = _overlap_score(battlefield)
    task_score = _overlap_score(task)
    audience_score = _overlap_score(audience)
    market_threat = _market_threat_score(market, str(pool.price_relation))
    evidence_score = _evidence_completeness_score(item)

    drafts: dict[M13ComponentCode, _ComponentDraft] = {}
    drafts[M13ComponentCode.SIZE_FIT] = _component(
        M13ComponentCode.SIZE_FIT,
        size_score,
        _feature_confidence(param, item),
        f"尺寸关系为{_size_relation_cn(str(pool.size_relation))}，用于判断是否在同一大屏比较区间。",
        param,
        _feature_evidence(param, item),
        gap_cn="尺寸信息不足，后续只能按弱可比处理。" if size_score < Decimal("0.3500") else None,
    )
    drafts[M13ComponentCode.PRICE_POSITION] = _component(
        M13ComponentCode.PRICE_POSITION,
        price_position_score,
        _feature_confidence(price, item),
        f"价位关系为{_price_relation_cn(str(pool.price_relation))}，用于判断双方是否会被放在同一价格决策集合。",
        price,
        _feature_evidence(market, item),
    )
    drafts[M13ComponentCode.CHANNEL_OVERLAP] = _component(
        M13ComponentCode.CHANNEL_OVERLAP,
        channel_score,
        _feature_confidence(channel, item),
        "渠道和平台重合度用于判断消费者是否会在同一货架或平台内比较两款 SKU。",
        channel,
        _feature_evidence(channel, item),
        gap_cn="渠道或平台重合不足，不能仅凭语义相似判断正面对打。" if channel_score < Decimal("0.3500") else None,
    )
    drafts[M13ComponentCode.BASE_COMPARABILITY] = _component(
        M13ComponentCode.BASE_COMPARABILITY,
        _avg_decimal([size_score, price_position_score, channel_score, _decimal(pool.recall_priority_score)]),
        _avg_decimal([drafts[M13ComponentCode.SIZE_FIT].confidence, drafts[M13ComponentCode.PRICE_POSITION].confidence, drafts[M13ComponentCode.CHANNEL_OVERLAP].confidence]),
        "综合尺寸、价位、渠道和 M12 召回强度，判断候选是否具备进入竞品评分的基本可比基础。",
        {
            "size_relation": pool.size_relation,
            "price_relation": pool.price_relation,
            "recall_priority_score": _float(pool.recall_priority_score),
            "channel_score": _float(channel_score),
        },
        _unique_evidence_ids([pool.evidence_ids or (), _feature_evidence(channel, item), _feature_evidence(market, item)]),
    )
    drafts[M13ComponentCode.BATTLEFIELD_FIT] = _component(
        M13ComponentCode.BATTLEFIELD_FIT,
        battlefield_score,
        _feature_confidence(battlefield, item),
        _overlap_summary("价值战场", battlefield),
        battlefield,
        _feature_evidence(battlefield, item),
        gap_cn="未发现共同价值战场，不能把该候选解释为主战场正面对打。" if battlefield_score < Decimal("0.2500") else None,
    )
    drafts[M13ComponentCode.TASK_OVERLAP] = _component(
        M13ComponentCode.TASK_OVERLAP,
        task_score,
        _feature_confidence(task, item),
        _overlap_summary("用户任务", task),
        task,
        _feature_evidence(task, item),
    )
    drafts[M13ComponentCode.AUDIENCE_OVERLAP] = _component(
        M13ComponentCode.AUDIENCE_OVERLAP,
        audience_score,
        _feature_confidence(audience, item),
        _overlap_summary("目标客群", audience),
        audience,
        _feature_evidence(audience, item),
    )
    drafts[M13ComponentCode.PARAM_SIMILARITY] = _component(
        M13ComponentCode.PARAM_SIMILARITY,
        param_similarity,
        _feature_confidence(param, item),
        "参数相似度基于 M08/M12 已抽取的核心参数共现和同值情况，说明产品能力是否处在同一比较口径。",
        param,
        _feature_evidence(param, item),
    )
    param_superiority = _param_superiority_score(param, str(pool.size_relation), str(pool.price_relation), claim)
    drafts[M13ComponentCode.PARAM_SUPERIORITY] = _component(
        M13ComponentCode.PARAM_SUPERIORITY,
        param_superiority,
        _feature_confidence(param, item),
        "参数优势压力用于识别候选是否通过尺寸、配置或同价更强参数形成拦截。",
        {
            "param_feature": param,
            "size_relation": pool.size_relation,
            "price_relation": pool.price_relation,
        },
        _feature_evidence(param, item),
        gap_cn="参数优势证据不足，不能写成候选配置明显领先。" if param_superiority < Decimal("0.3500") else None,
    )
    drafts[M13ComponentCode.CLAIM_CONFRONTATION] = _component(
        M13ComponentCode.CLAIM_CONFRONTATION,
        claim_confrontation,
        _feature_confidence(claim, item),
        _claim_summary(claim),
        claim,
        _feature_evidence(claim, item),
        gap_cn="缺少战场内卖点价值重合，不能证明卖点正面对打。" if claim_confrontation < Decimal("0.2500") else None,
    )
    claim_superiority = _claim_superiority_score(claim)
    drafts[M13ComponentCode.CLAIM_SUPERIORITY] = _component(
        M13ComponentCode.CLAIM_SUPERIORITY,
        claim_superiority,
        _feature_confidence(claim, item),
        "卖点优势压力基于 M11.5 分层结果，判断候选是否在共同战场卖点上更强。",
        claim,
        _feature_evidence(claim, item),
    )
    threshold_sufficiency = _claim_threshold_sufficiency_score(claim)
    drafts[M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY] = _component(
        M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY,
        threshold_sufficiency,
        _feature_confidence(claim, item),
        "门槛卖点满足度用于判断候选是否至少具备同战场比较所需的基础卖点。",
        claim,
        _feature_evidence(claim, item),
    )
    price_advantage = _price_advantage_score(str(pool.price_relation), price)
    drafts[M13ComponentCode.PRICE_ADVANTAGE] = _component(
        M13ComponentCode.PRICE_ADVANTAGE,
        price_advantage,
        _feature_confidence(price, item),
        "价格拦截力度判断候选是否以更低或更有吸引力价格影响目标 SKU 的选择。",
        price,
        _feature_evidence(market, item),
    )
    drafts[M13ComponentCode.MARKET_THREAT] = _component(
        M13ComponentCode.MARKET_THREAT,
        market_threat,
        _feature_confidence(market, item),
        "市场压力基于已清洗市场画像和 M12 快照中的销量/销额相对强度，不回读原始销售表。",
        market,
        _feature_evidence(market, item),
    )
    sales_amount_strength = _sales_amount_score(market)
    drafts[M13ComponentCode.SALES_AMOUNT_STRENGTH] = _component(
        M13ComponentCode.SALES_AMOUNT_STRENGTH,
        sales_amount_strength,
        _feature_confidence(market, item),
        "销额强度用于判断候选是否在同场比较中已有足够成交权重。",
        _dict(market.get("sales")),
        _feature_evidence(market, item),
    )
    comment_perception = _comment_perception_score(quality)
    drafts[M13ComponentCode.COMMENT_PERCEPTION] = _component(
        M13ComponentCode.COMMENT_PERCEPTION,
        comment_perception,
        _feature_confidence(quality, item),
        "评论感知只使用上游画像中已形成的质量和风险摘要，用于补充体验侧可信度。",
        quality,
        _feature_evidence(quality, item),
        risk_flags=tuple(quality.get("candidate_risk_signals") or ()),
    )
    price_trend = _price_trend_score(str(pool.price_relation), price, market)
    drafts[M13ComponentCode.PRICE_TREND] = _component(
        M13ComponentCode.PRICE_TREND,
        price_trend,
        _feature_confidence(market, item),
        "价格趋势压力目前基于 M07/M12 快照中的价差和价格关系，后续真实增量数据补齐后可纳入趋势字段。",
        {"price": price, "market_sample_status": market.get("sample_status")},
        _feature_evidence(market, item),
    )
    drafts[M13ComponentCode.EVIDENCE_COMPLETENESS] = _component(
        M13ComponentCode.EVIDENCE_COMPLETENESS,
        evidence_score,
        Decimal("0.9500") if evidence_score >= Decimal("0.5000") else Decimal("0.6500"),
        "证据完整度衡量该 pair 是否同时具备市场、语义、卖点和评论/质量侧支撑。",
        {
            "reason_count": len(item.reasons),
            "source_count": len({str(reason.recall_source) for reason in item.reasons}),
            "evidence_count": len(_unique_evidence_ids([pool.evidence_ids or (), snapshot.evidence_ids or ()])),
        },
        _unique_evidence_ids([pool.evidence_ids or (), snapshot.evidence_ids or ()]),
        gap_cn="证据来源不足，后续入选必须标注复核。" if evidence_score < Decimal("0.4500") else None,
    )
    return drafts


def _component(
    code: M13ComponentCode,
    score: Decimal,
    confidence: Decimal,
    summary_cn: str,
    source_payload: Mapping[str, Any],
    evidence_ids: Sequence[str],
    *,
    gap_cn: str | None = None,
    risk_flags: tuple[dict[str, Any] | str, ...] = (),
) -> _ComponentDraft:
    normalized_score = _clamp_decimal(score)
    normalized_confidence = _clamp_decimal(confidence)
    support = _support_level(normalized_score, normalized_confidence)
    return _ComponentDraft(
        code=code,
        score=normalized_score,
        confidence=normalized_confidence,
        support_level=support,
        summary_cn=summary_cn,
        positive_summary_cn=summary_cn if normalized_score >= Decimal("0.5000") else None,
        gap_summary_cn=gap_cn,
        source_payload=dict(source_payload),
        evidence_ids=tuple(evidence_ids),
        missing_reasons=({"reason_cn": gap_cn},) if gap_cn else (),
        risk_flags=risk_flags,
    )


def _build_role_scores(
    components: Mapping[M13ComponentCode, _ComponentDraft],
    item: M13CandidateInput,
) -> dict[M13RoleCode, Decimal]:
    scores = {
        role_code: _weighted_score(
            {component: components[component].score for component in weights if component in components},
            weights,
        )
        for role_code, weights in ROLE_COMPONENT_WEIGHTS.items()
    }
    relation_types = {str(value) for value in item.pool.relation_types_json or ()}
    if "service_reference" not in relation_types:
        scores[M13RoleCode.SERVICE_REFERENCE] = min(scores[M13RoleCode.SERVICE_REFERENCE], Decimal("0.4200"))
    if str(item.pool.recall_strength) == "review_only":
        for role in (M13RoleCode.DIRECT_FIGHT, M13RoleCode.PRICE_VOLUME_PRESSURE, M13RoleCode.BENCHMARK_POTENTIAL):
            scores[role] = min(scores[role], Decimal("0.5000"))
    evidence_score = components[M13ComponentCode.EVIDENCE_COMPLETENESS].score
    if evidence_score < Decimal("0.4500"):
        for role in (M13RoleCode.DIRECT_FIGHT, M13RoleCode.PRICE_VOLUME_PRESSURE, M13RoleCode.BENCHMARK_POTENTIAL):
            scores[role] = min(scores[role], Decimal("0.6200"))
    return {role_code: _quantize(score) for role_code, score in scores.items()}


def _role_record(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    item: M13CandidateInput,
    component_score_id: str,
    role_code: M13RoleCode,
    role_score: Decimal,
    components: Mapping[M13ComponentCode, _ComponentDraft],
    pair_confidence: Decimal,
) -> M13CandidateRoleScoreRecord:
    pool = item.pool
    snapshot = item.snapshot
    if snapshot is None:
        raise M13InputBlockedError("M13 role record requires feature snapshot")
    contributions = _role_contributions(role_code, components)
    auto_select_eligible = _auto_select_eligible(role_code, role_score, pair_confidence, components)
    block_reason = None if auto_select_eligible else _auto_select_block_reason(role_score, pair_confidence, components)
    input_payload = {
        "candidate_pool_id": pool.candidate_pool_id,
        "feature_snapshot_hash": snapshot.feature_snapshot_hash,
        "role_code": role_code.value,
        "rule_version": rule_version,
    }
    return M13CandidateRoleScoreRecord(
        candidate_role_score_id=_record_id("m13role", batch_id, pool.target_sku_code, pool.candidate_sku_code, role_code.value, rule_version),
        candidate_component_score_id=component_score_id,
        candidate_pool_id=pool.candidate_pool_id,
        feature_snapshot_id=snapshot.candidate_feature_snapshot_id,
        project_id=pool.project_id,
        category_code=pool.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=pool.target_sku_code,
        candidate_sku_code=pool.candidate_sku_code,
        role_code=role_code,
        role_name_cn=ROLE_LABEL_CN[role_code],
        role_score=role_score,
        role_confidence=_role_confidence(role_score, pair_confidence, components),
        auto_select_eligible=auto_select_eligible,
        auto_select_block_reason=block_reason,
        role_business_reason_cn=_role_reason_cn(role_code, role_score, contributions),
        role_business_reason_short_cn=f"{ROLE_LABEL_CN[role_code]}分 {role_score:.2f}，{_top_contribution_text(contributions)}。",
        formula_version=CORE3_M13_ROLE_RULE_VERSION,
        component_contribution_json=contributions,
        positive_evidence_ids=_unique_evidence_ids(draft.evidence_ids for draft in components.values() if draft.score >= Decimal("0.4500")),
        weakening_evidence_ids=_unique_evidence_ids(draft.weakening_evidence_ids for draft in components.values()),
        risk_flags_json=_role_risk_flags(role_code, role_score, components, pair_confidence),
        review_required=not auto_select_eligible and role_score >= Decimal("0.6500"),
        review_reason=block_reason if role_score >= Decimal("0.6500") else None,
        rule_version=rule_version,
        input_fingerprint=stable_hash(input_payload, version="m13_role_input_v1"),
        result_hash=stable_hash({**input_payload, "score": role_score, "contributions": contributions}, version="m13_role_result_v1"),
    )


def _explanation_record(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    item: M13CandidateInput,
    component_score_id: str,
    component: _ComponentDraft,
) -> M13CandidateComponentExplanationRecord:
    pool = item.pool
    snapshot = item.snapshot
    if snapshot is None:
        raise M13InputBlockedError("M13 explanation requires feature snapshot")
    input_payload = {
        "candidate_pool_id": pool.candidate_pool_id,
        "feature_snapshot_hash": snapshot.feature_snapshot_hash,
        "component_code": component.code.value,
        "rule_version": rule_version,
    }
    return M13CandidateComponentExplanationRecord(
        candidate_component_explanation_id=_record_id("m13exp", batch_id, pool.target_sku_code, pool.candidate_sku_code, component.code.value, rule_version),
        candidate_component_score_id=component_score_id,
        candidate_pool_id=pool.candidate_pool_id,
        feature_snapshot_id=snapshot.candidate_feature_snapshot_id,
        project_id=pool.project_id,
        category_code=pool.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=pool.target_sku_code,
        candidate_sku_code=pool.candidate_sku_code,
        component_code=component.code,
        component_name_cn=COMPONENT_LABEL_CN[component.code],
        score=component.score,
        confidence=component.confidence,
        support_level=component.support_level,
        business_explanation_cn=(
            f"{COMPONENT_LABEL_CN[component.code]}：{component.summary_cn}"
            f"当前组件分 {component.score:.2f}，置信度 {component.confidence:.2f}。"
        ),
        positive_summary_cn=component.positive_summary_cn,
        gap_summary_cn=component.gap_summary_cn,
        supporting_evidence_ids=list(component.evidence_ids),
        weakening_evidence_ids=list(component.weakening_evidence_ids),
        missing_evidence_reasons_json=list(component.missing_reasons),
        source_payload_json=component.source_payload,
        risk_flags_json=list(component.risk_flags),
        rule_version=rule_version,
        input_fingerprint=stable_hash(input_payload, version="m13_explanation_input_v1"),
        result_hash=stable_hash(
            {**input_payload, "score": component.score, "confidence": component.confidence, "summary": component.summary_cn},
            version="m13_explanation_result_v1",
        ),
    )


def _review_issues(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    item: M13CandidateInput,
    component_score_id: str,
    components: Mapping[M13ComponentCode, _ComponentDraft],
    role_scores: Mapping[M13RoleCode, Decimal],
    pair_confidence: Decimal,
    total_score: Decimal,
) -> list[M13CandidateScoreReviewIssueRecord]:
    issues: list[M13CandidateScoreReviewIssueRecord] = []
    if components[M13ComponentCode.EVIDENCE_COMPLETENESS].score < Decimal("0.4500"):
        issues.append(
            _issue_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                issue_type=M13ReviewIssueType.SAMPLE_INSUFFICIENT.value,
                issue_level=M13IssueLevel.REVIEW,
                issue_scope=M13IssueScope.EVIDENCE,
                component_code=M13ComponentCode.EVIDENCE_COMPLETENESS.value,
                message_cn="该候选评分证据完整度不足，M14 不能自动入选。",
                suggested_action_cn="补齐市场、卖点或评论证据，或在 M16 人工复核后再使用。",
                evidence_ids=components[M13ComponentCode.EVIDENCE_COMPLETENESS].evidence_ids,
            )
        )
    semantic_max = max(
        components[M13ComponentCode.BATTLEFIELD_FIT].score,
        components[M13ComponentCode.TASK_OVERLAP].score,
        components[M13ComponentCode.AUDIENCE_OVERLAP].score,
        components[M13ComponentCode.CLAIM_CONFRONTATION].score,
    )
    if semantic_max < Decimal("0.2500"):
        issues.append(
            _issue_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                issue_type=M13ReviewIssueType.NO_SEMANTIC_EVIDENCE.value,
                issue_level=M13IssueLevel.REVIEW,
                issue_scope=M13IssueScope.PAIR,
                message_cn="该候选缺少任务、客群、战场或卖点语义证据，不能只凭价格销量解释为竞品。",
                suggested_action_cn="M14 如保留该候选，必须标注为市场压力或复核候选。",
            )
        )
    if components[M13ComponentCode.CLAIM_CONFRONTATION].score < Decimal("0.2500"):
        issues.append(
            _issue_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                issue_type=M13ReviewIssueType.CLAIM_MISSING.value,
                issue_level=M13IssueLevel.WARNING,
                issue_scope=M13IssueScope.COMPONENT,
                component_code=M13ComponentCode.CLAIM_CONFRONTATION.value,
                message_cn="该候选缺少战场内卖点对打证据，后续页面不能写成卖点正面对打。",
                suggested_action_cn="M15 证据卡应把卖点证据写为缺口或待复核。",
                evidence_ids=components[M13ComponentCode.CLAIM_CONFRONTATION].evidence_ids,
            )
        )
    if total_score >= Decimal("0.6500") and pair_confidence < Decimal("0.5500"):
        issues.append(
            _issue_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                issue_type=M13ReviewIssueType.HIGH_SCORE_LOW_CONFIDENCE.value,
                issue_level=M13IssueLevel.REVIEW,
                issue_scope=M13IssueScope.PAIR,
                message_cn="该候选组件分较高但置信度不足，不能直接进入核心三竞品自动选择。",
                suggested_action_cn="优先补齐缺失证据或进入 M16 人工复核。",
            )
        )
    if role_scores[M13RoleCode.SERVICE_REFERENCE] > max(
        role_scores[M13RoleCode.DIRECT_FIGHT],
        role_scores[M13RoleCode.PRICE_VOLUME_PRESSURE],
        role_scores[M13RoleCode.BENCHMARK_POTENTIAL],
    ):
        issues.append(
            _issue_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                item=item,
                component_score_id=component_score_id,
                issue_type=M13ReviewIssueType.SERVICE_OVER_WEIGHTED.value,
                issue_level=M13IssueLevel.WARNING,
                issue_scope=M13IssueScope.ROLE,
                role_code=M13RoleCode.SERVICE_REFERENCE.value,
                message_cn="该候选主要体现服务参照价值，不应被表达为产品正面对打竞品。",
                suggested_action_cn="M14 可作为服务参照候选，但不得占用正面对打槽位。",
            )
        )
    return issues


def _issue_record(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    item: M13CandidateInput,
    component_score_id: str | None,
    issue_type: str,
    issue_level: M13IssueLevel,
    issue_scope: M13IssueScope,
    message_cn: str,
    suggested_action_cn: str,
    component_code: str = "",
    role_code: str = "",
    evidence_ids: Sequence[str] = (),
) -> M13CandidateScoreReviewIssueRecord:
    pool = item.pool
    snapshot = item.snapshot
    input_payload = {
        "candidate_pool_id": pool.candidate_pool_id,
        "feature_snapshot_id": snapshot.candidate_feature_snapshot_id if snapshot else None,
        "issue_type": issue_type,
        "issue_scope": issue_scope.value,
        "component_code": component_code,
        "role_code": role_code,
        "message_cn": message_cn,
    }
    fingerprint = stable_hash(input_payload, version="m13_review_issue_input_v1")
    return M13CandidateScoreReviewIssueRecord(
        candidate_score_review_issue_id=_record_id(
            "m13issue",
            batch_id,
            pool.target_sku_code,
            pool.candidate_sku_code,
            issue_scope.value,
            component_code,
            role_code,
            issue_type,
            fingerprint,
        ),
        candidate_component_score_id=component_score_id,
        candidate_pool_id=pool.candidate_pool_id,
        feature_snapshot_id=snapshot.candidate_feature_snapshot_id if snapshot else None,
        project_id=pool.project_id,
        category_code=pool.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=pool.target_sku_code,
        candidate_sku_code=pool.candidate_sku_code,
        issue_scope=issue_scope,
        component_code=component_code,
        role_code=role_code,
        issue_type=issue_type,
        issue_level=issue_level,
        issue_message_cn=message_cn,
        suggested_action_cn=suggested_action_cn,
        source_payload_json=input_payload,
        evidence_ids=list(evidence_ids),
        rule_version=rule_version,
        input_fingerprint=fingerprint,
        result_hash=stable_hash({**input_payload, "suggested_action_cn": suggested_action_cn}, version="m13_review_issue_result_v1"),
        review_reason_json={"issue_type": issue_type, "issue_scope": issue_scope.value},
    )


def _snapshot_source(snapshot: entities.Core3CandidateFeatureSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    source = _dict(snapshot.m13_component_input_json)
    fallbacks = {
        "size_feature": snapshot.size_feature_json,
        "price_feature": snapshot.price_feature_json,
        "channel_feature": snapshot.channel_feature_json,
        "market_feature": snapshot.market_feature_json,
        "param_feature": snapshot.param_feature_json,
        "battlefield_overlap": snapshot.battlefield_overlap_json,
        "task_overlap": snapshot.task_overlap_json,
        "audience_overlap": snapshot.audience_overlap_json,
        "claim_value_overlap": snapshot.claim_value_overlap_json,
        "quality_feature": snapshot.quality_feature_json,
    }
    for key, value in fallbacks.items():
        source.setdefault(key, value or {})
    return source


def _component_payload_json(
    components: Mapping[M13ComponentCode, _ComponentDraft],
    role_scores: Mapping[M13RoleCode, Decimal],
) -> dict[str, Any]:
    return {
        "boundary_note": BOUNDARY_NOTE_CN,
        "components": {
            code.value: {
                "component_name_cn": COMPONENT_LABEL_CN[code],
                "score": _float(draft.score),
                "confidence": _float(draft.confidence),
                "support_level": draft.support_level.value,
                "summary_cn": draft.summary_cn,
                "evidence_count": len(draft.evidence_ids),
            }
            for code, draft in components.items()
        },
        "role_scores": {role.value: _float(score) for role, score in role_scores.items()},
    }


def _main_strengths(components: Mapping[M13ComponentCode, _ComponentDraft]) -> list[dict[str, Any]]:
    sorted_items = sorted(components.values(), key=lambda draft: (draft.score, draft.confidence), reverse=True)
    return [
        {
            "component_code": draft.code.value,
            "component_name_cn": COMPONENT_LABEL_CN[draft.code],
            "score": _float(draft.score),
            "reason_cn": draft.summary_cn,
        }
        for draft in sorted_items
        if draft.score >= Decimal("0.5500")
    ][:5]


def _main_gaps(components: Mapping[M13ComponentCode, _ComponentDraft]) -> list[dict[str, Any]]:
    sorted_items = sorted(components.values(), key=lambda draft: (draft.score, draft.confidence))
    return [
        {
            "component_code": draft.code.value,
            "component_name_cn": COMPONENT_LABEL_CN[draft.code],
            "score": _float(draft.score),
            "gap_cn": draft.gap_summary_cn or "该组件支撑较弱，需要谨慎表达。",
        }
        for draft in sorted_items
        if draft.score < Decimal("0.3500")
    ][:5]


def _pair_risk_flags(
    components: Mapping[M13ComponentCode, _ComponentDraft],
    pool: entities.Core3CandidatePool,
    role_scores: Mapping[M13RoleCode, Decimal],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = list(pool.risk_flags_json or ())
    if components[M13ComponentCode.EVIDENCE_COMPLETENESS].score < Decimal("0.4500"):
        flags.append({"issue_type": M13ReviewIssueType.SAMPLE_INSUFFICIENT.value, "reason_cn": "证据完整度不足。"})
    if components[M13ComponentCode.CLAIM_CONFRONTATION].score < Decimal("0.2500"):
        flags.append({"issue_type": M13ReviewIssueType.CLAIM_MISSING.value, "reason_cn": "缺少卖点价值对打证据。"})
    if role_scores[M13RoleCode.SERVICE_REFERENCE] > role_scores[M13RoleCode.DIRECT_FIGHT]:
        flags.append({"issue_type": M13ReviewIssueType.SERVICE_OVER_WEIGHTED.value, "reason_cn": "服务参照高于产品正面对打。"})
    return flags


def _component_review_state(
    components: Mapping[M13ComponentCode, _ComponentDraft],
    role_scores: Mapping[M13RoleCode, Decimal],
    pool: entities.Core3CandidatePool,
    confidence: Decimal,
) -> tuple[bool, str | None]:
    if components[M13ComponentCode.EVIDENCE_COMPLETENESS].score < Decimal("0.4500"):
        return True, M13ReviewIssueType.SAMPLE_INSUFFICIENT.value
    if max(
        components[M13ComponentCode.BATTLEFIELD_FIT].score,
        components[M13ComponentCode.TASK_OVERLAP].score,
        components[M13ComponentCode.AUDIENCE_OVERLAP].score,
        components[M13ComponentCode.CLAIM_CONFRONTATION].score,
    ) < Decimal("0.2500"):
        return True, M13ReviewIssueType.NO_SEMANTIC_EVIDENCE.value
    if str(pool.recall_strength) == "review_only":
        return True, M13ReviewIssueType.ONLY_SERVICE_SIGNAL.value
    if max(role_scores.values()) >= Decimal("0.6500") and confidence < Decimal("0.5500"):
        return True, M13ReviewIssueType.HIGH_SCORE_LOW_CONFIDENCE.value
    return False, None


def _role_contributions(
    role_code: M13RoleCode,
    components: Mapping[M13ComponentCode, _ComponentDraft],
) -> dict[str, Any]:
    weights = ROLE_COMPONENT_WEIGHTS[role_code]
    total_weight = sum(weights.values(), Decimal("0"))
    items = []
    for component_code, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
        draft = components[component_code]
        items.append(
            {
                "component_code": component_code.value,
                "component_name_cn": COMPONENT_LABEL_CN[component_code],
                "component_score": _float(draft.score),
                "weight": _float(weight / total_weight if total_weight else Decimal("0")),
                "weighted_score": _float(draft.score * weight / total_weight if total_weight else Decimal("0")),
                "summary_cn": draft.summary_cn,
            }
        )
    return {"role_code": role_code.value, "role_name_cn": ROLE_LABEL_CN[role_code], "items": items}


def _role_reason_cn(role_code: M13RoleCode, role_score: Decimal, contributions: Mapping[str, Any]) -> str:
    top_items = list(contributions.get("items") or [])[:3]
    top_text = "、".join(f"{item['component_name_cn']} {item['component_score']:.2f}" for item in top_items)
    return (
        f"{ROLE_LABEL_CN[role_code]}角色分为 {role_score:.2f}，主要由{top_text}支撑。"
        "该角色分只服务 M14 槽位选择，不代表最终核心竞品结论。"
    )


def _top_contribution_text(contributions: Mapping[str, Any]) -> str:
    items = list(contributions.get("items") or [])
    if not items:
        return "缺少可解释组件支撑"
    top = items[0]
    return f"主要来自{top['component_name_cn']}"


def _role_confidence(
    role_score: Decimal,
    pair_confidence: Decimal,
    components: Mapping[M13ComponentCode, _ComponentDraft],
) -> Decimal:
    evidence_score = components[M13ComponentCode.EVIDENCE_COMPLETENESS].score
    return _clamp_decimal(pair_confidence * Decimal("0.70") + evidence_score * Decimal("0.20") + role_score * Decimal("0.10"))


def _auto_select_eligible(
    role_code: M13RoleCode,
    role_score: Decimal,
    pair_confidence: Decimal,
    components: Mapping[M13ComponentCode, _ComponentDraft],
) -> bool:
    if role_code == M13RoleCode.SERVICE_REFERENCE:
        return role_score >= Decimal("0.6000") and pair_confidence >= Decimal("0.5500")
    return (
        role_score >= Decimal("0.6200")
        and pair_confidence >= Decimal("0.5500")
        and components[M13ComponentCode.EVIDENCE_COMPLETENESS].score >= Decimal("0.4500")
    )


def _auto_select_block_reason(
    role_score: Decimal,
    pair_confidence: Decimal,
    components: Mapping[M13ComponentCode, _ComponentDraft],
) -> str:
    if role_score < Decimal("0.6200"):
        return "role_score_below_threshold"
    if pair_confidence < Decimal("0.5500"):
        return "confidence_below_threshold"
    if components[M13ComponentCode.EVIDENCE_COMPLETENESS].score < Decimal("0.4500"):
        return "evidence_completeness_below_threshold"
    return "manual_review_required"


def _role_risk_flags(
    role_code: M13RoleCode,
    role_score: Decimal,
    components: Mapping[M13ComponentCode, _ComponentDraft],
    pair_confidence: Decimal,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if role_score >= Decimal("0.6500") and pair_confidence < Decimal("0.5500"):
        flags.append({"issue_type": M13ReviewIssueType.HIGH_SCORE_LOW_CONFIDENCE.value, "reason_cn": "角色分较高但整体置信度不足。"})
    if role_code == M13RoleCode.DIRECT_FIGHT and components[M13ComponentCode.CLAIM_CONFRONTATION].score < Decimal("0.2500"):
        flags.append({"issue_type": M13ReviewIssueType.CLAIM_MISSING.value, "reason_cn": "正面对打缺少卖点对打支撑。"})
    return flags


def _pair_confidence(components: Mapping[M13ComponentCode, _ComponentDraft], pool: entities.Core3CandidatePool) -> Decimal:
    component_conf = _avg_decimal(draft.confidence for draft in components.values())
    evidence_score = components[M13ComponentCode.EVIDENCE_COMPLETENESS].score
    score = component_conf * Decimal("0.65") + evidence_score * Decimal("0.35")
    if str(pool.recall_strength) == "review_only":
        score = min(score, Decimal("0.5000"))
    elif str(pool.recall_strength) == "weak":
        score = min(score, Decimal("0.7200"))
    return _clamp_decimal(score)


def _weighted_score(scores: Mapping[M13ComponentCode, Decimal], weights: Mapping[M13ComponentCode, Decimal]) -> Decimal:
    total_weight = sum(weights.values(), Decimal("0"))
    if total_weight <= 0:
        return Decimal("0.0000")
    score = sum(_decimal(scores.get(code)) * weight for code, weight in weights.items()) / total_weight
    return _clamp_decimal(score)


def _size_score(size_relation: str, param: Mapping[str, Any]) -> Decimal:
    if size_relation == "same":
        return Decimal("0.9500")
    if size_relation in {"adjacent_larger", "adjacent_smaller"}:
        return Decimal("0.7200")
    if size_relation in {"larger_cross", "smaller_cross"}:
        return Decimal("0.4800")
    size = _dict(param.get("size"))
    if size.get("target_size") and size.get("candidate_size"):
        target = _decimal(size.get("target_size"))
        candidate = _decimal(size.get("candidate_size"))
        if target and candidate and abs(target - candidate) <= Decimal("5"):
            return Decimal("0.6500")
    return Decimal("0.2500")


def _price_position_score(price_relation: str, price: Mapping[str, Any]) -> Decimal:
    if price_relation == "similar":
        return Decimal("0.9000")
    if price_relation in {"lower", "higher"}:
        return Decimal("0.6500")
    gap_pct = _decimal(price.get("price_gap_pct_to_target"))
    if gap_pct != Decimal("0"):
        if abs(gap_pct) <= Decimal("0.1200"):
            return Decimal("0.8500")
        if abs(gap_pct) <= Decimal("0.2500"):
            return Decimal("0.6200")
    return Decimal("0.3000")


def _price_advantage_score(price_relation: str, price: Mapping[str, Any]) -> Decimal:
    if price_relation == "lower":
        return Decimal("0.8500")
    if price_relation == "similar":
        return Decimal("0.5200")
    if price_relation == "higher":
        return Decimal("0.2500")
    gap_pct = _decimal(price.get("price_gap_pct_to_target"))
    if gap_pct < 0:
        return _clamp_decimal(Decimal("0.5500") + min(abs(gap_pct), Decimal("0.3000")))
    return Decimal("0.2500")


def _channel_score(channel: Mapping[str, Any]) -> Decimal:
    platform = _decimal(channel.get("platform_overlap_score"))
    channel_score = _decimal(channel.get("channel_overlap_score"))
    if platform == 0 and channel_score == 0:
        same_channel = bool(channel.get("target_main_channel") and channel.get("target_main_channel") == channel.get("candidate_main_channel"))
        same_platform = bool(channel.get("target_main_platform") and channel.get("target_main_platform") == channel.get("candidate_main_platform"))
        if same_channel and same_platform:
            return Decimal("0.8000")
        if same_channel or same_platform:
            return Decimal("0.5500")
        return Decimal("0.2500")
    return _clamp_decimal(max(platform, channel_score))


def _param_similarity_score(param: Mapping[str, Any]) -> Decimal:
    shared = list(param.get("shared_param_codes") or ())
    same = list(param.get("same_value_param_codes") or ())
    if not shared:
        return Decimal("0.2000")
    same_ratio = Decimal(len(same)) / Decimal(max(len(shared), 1))
    shared_depth = min(Decimal(len(shared)) / Decimal("8"), Decimal("1.0000"))
    return _clamp_decimal(same_ratio * Decimal("0.75") + shared_depth * Decimal("0.25"))


def _param_superiority_score(param: Mapping[str, Any], size_relation: str, price_relation: str, claim: Mapping[str, Any]) -> Decimal:
    score = Decimal("0.2500")
    if size_relation in {"adjacent_larger", "larger_cross"}:
        score += Decimal("0.1800")
    if price_relation in {"lower", "similar"}:
        score += Decimal("0.1000")
    candidate_stronger = _decimal(claim.get("candidate_stronger_count"))
    matched_count = _decimal(claim.get("matched_count"))
    if matched_count:
        score += min(candidate_stronger / matched_count, Decimal("1.0000")) * Decimal("0.2500")
    shared = len(param.get("shared_param_codes") or ())
    same = len(param.get("same_value_param_codes") or ())
    if shared and same / max(shared, 1) >= 0.6:
        score += Decimal("0.1000")
    return _clamp_decimal(score)


def _claim_superiority_score(claim: Mapping[str, Any]) -> Decimal:
    matched = _decimal(claim.get("matched_count"))
    if matched <= 0:
        return Decimal("0.1800")
    candidate = _decimal(claim.get("candidate_stronger_count"))
    target = _decimal(claim.get("target_stronger_count"))
    base = _decimal(claim.get("overlap_score")) * Decimal("0.45")
    advantage = max(candidate - target, Decimal("0")) / max(matched, Decimal("1")) * Decimal("0.55")
    return _clamp_decimal(base + advantage)


def _claim_threshold_sufficiency_score(claim: Mapping[str, Any]) -> Decimal:
    matched = _decimal(claim.get("matched_count"))
    if matched <= 0:
        return Decimal("0.1500")
    overlap = _decimal(claim.get("overlap_score"))
    density = min(matched / Decimal("4"), Decimal("1.0000"))
    return _clamp_decimal(overlap * Decimal("0.65") + density * Decimal("0.35"))


def _market_threat_score(market: Mapping[str, Any], price_relation: str) -> Decimal:
    sales = _dict(market.get("sales"))
    target_volume = _decimal(sales.get("target_volume"))
    candidate_volume = _decimal(sales.get("candidate_volume"))
    target_amount = _decimal(sales.get("target_amount"))
    candidate_amount = _decimal(sales.get("candidate_amount"))
    volume_ratio = candidate_volume / target_volume if target_volume > 0 else Decimal("0")
    amount_ratio = candidate_amount / target_amount if target_amount > 0 else Decimal("0")
    score = min(volume_ratio, Decimal("1.2500")) / Decimal("1.2500") * Decimal("0.45")
    score += min(amount_ratio, Decimal("1.2500")) / Decimal("1.2500") * Decimal("0.40")
    if price_relation == "lower":
        score += Decimal("0.1000")
    elif price_relation == "similar":
        score += Decimal("0.0700")
    return _clamp_decimal(score)


def _sales_amount_score(market: Mapping[str, Any]) -> Decimal:
    sales = _dict(market.get("sales"))
    target_amount = _decimal(sales.get("target_amount"))
    candidate_amount = _decimal(sales.get("candidate_amount"))
    if target_amount <= 0 or candidate_amount <= 0:
        return Decimal("0.2000")
    return _clamp_decimal(min(candidate_amount / target_amount, Decimal("1.2000")) / Decimal("1.2000"))


def _comment_perception_score(quality: Mapping[str, Any]) -> Decimal:
    target_conf = _decimal(quality.get("target_confidence"))
    candidate_conf = _decimal(quality.get("candidate_confidence"))
    risk_penalty = Decimal("0.0500") * Decimal(len(quality.get("candidate_risk_signals") or ()))
    missing_penalty = Decimal("0.0300") * Decimal(len(quality.get("candidate_missing_signals") or ()))
    return _clamp_decimal(_avg_decimal([target_conf, candidate_conf]) - risk_penalty - missing_penalty)


def _price_trend_score(price_relation: str, price: Mapping[str, Any], market: Mapping[str, Any]) -> Decimal:
    score = Decimal("0.3000")
    if price_relation == "lower":
        score = Decimal("0.6800")
    elif price_relation == "similar":
        score = Decimal("0.5200")
    elif price_relation == "higher":
        score = Decimal("0.3500")
    gap_pct = _decimal(price.get("price_gap_pct_to_target"))
    if gap_pct < Decimal("-0.1500"):
        score += Decimal("0.1200")
    if str(market.get("sample_status")) in {"insufficient", "unknown"}:
        score = min(score, Decimal("0.5000"))
    return _clamp_decimal(score)


def _evidence_completeness_score(item: M13CandidateInput) -> Decimal:
    source_count = len({str(reason.recall_source) for reason in item.reasons})
    evidence_count = len(
        _unique_evidence_ids([item.pool.evidence_ids or (), item.snapshot.evidence_ids if item.snapshot else ()])
    )
    snapshot = _snapshot_source(item.snapshot)
    required_features = (
        "battlefield_overlap",
        "task_overlap",
        "audience_overlap",
        "claim_value_overlap",
        "market_feature",
        "param_feature",
        "quality_feature",
    )
    feature_score = Decimal(sum(1 for key in required_features if _has_signal(_dict(snapshot.get(key))))) / Decimal(len(required_features))
    source_score = min(Decimal(source_count) / Decimal("5"), Decimal("1.0000"))
    evidence_score = min(Decimal(evidence_count) / Decimal("12"), Decimal("1.0000"))
    return _clamp_decimal(feature_score * Decimal("0.45") + source_score * Decimal("0.30") + evidence_score * Decimal("0.25"))


def _overlap_score(feature: Mapping[str, Any]) -> Decimal:
    explicit = _decimal(feature.get("overlap_score"))
    if explicit > 0:
        return _clamp_decimal(explicit)
    matched = len(feature.get("matched_codes") or feature.get("matched_claims") or ())
    if matched:
        return min(Decimal(matched) / Decimal("4"), Decimal("1.0000"))
    return Decimal("0.0000")


def _feature_confidence(feature: Mapping[str, Any], item: M13CandidateInput) -> Decimal:
    evidence = len(_feature_evidence(feature, item))
    signal = Decimal("0.2500") if _has_signal(feature) else Decimal("0.0000")
    evidence_score = min(Decimal(evidence) / Decimal("6"), Decimal("1.0000")) * Decimal("0.3500")
    pair_score = _clamp_decimal(_decimal(item.pool.evidence_quality_score)) * Decimal("0.4000")
    return _clamp_decimal(signal + evidence_score + pair_score)


def _feature_evidence(feature: Mapping[str, Any], item: M13CandidateInput) -> tuple[str, ...]:
    return tuple(_unique_evidence_ids([feature.get("evidence_ids") or (), item.pool.evidence_ids or ()]))


def _has_signal(feature: Mapping[str, Any]) -> bool:
    if not feature:
        return False
    for key, value in feature.items():
        if key.endswith("_ids"):
            continue
        if value not in (None, "", [], {}, 0, 0.0):
            return True
    return False


def _overlap_summary(name_cn: str, feature: Mapping[str, Any]) -> str:
    matched = list(feature.get("matched_codes") or ())
    if matched:
        return f"双方共同命中 {len(matched)} 个{name_cn}，说明存在同一购买语境或使用场景。"
    return f"当前未发现共同{name_cn}，该维度不能支撑正面对打判断。"


def _claim_summary(feature: Mapping[str, Any]) -> str:
    matched = list(feature.get("matched_claims") or ())
    if matched:
        return f"双方在 {len(matched)} 个战场内卖点价值上可比，能够支撑卖点对打解释。"
    return "当前没有共同战场内卖点价值，不能证明卖点正面对打。"


def _sample_status(pool: entities.Core3CandidatePool) -> M13SampleStatus:
    value = str(pool.sample_status or "")
    if value in {item.value for item in M13SampleStatus}:
        return M13SampleStatus(value)
    return M13SampleStatus.UNKNOWN


def _support_level(score: Decimal, confidence: Decimal) -> M13SupportLevel:
    if confidence < Decimal("0.2500") and score < Decimal("0.2500"):
        return M13SupportLevel.MISSING
    if score >= Decimal("0.7500") and confidence >= Decimal("0.5500"):
        return M13SupportLevel.STRONG
    if score >= Decimal("0.5000"):
        return M13SupportLevel.MEDIUM
    if score >= Decimal("0.2000"):
        return M13SupportLevel.WEAK
    return M13SupportLevel.MISSING


def _price_relation_cn(value: str) -> str:
    return {"lower": "候选更低价", "similar": "价位接近", "higher": "候选更高价"}.get(value, "价位待确认")


def _size_relation_cn(value: str) -> str:
    return {
        "same": "同尺寸",
        "adjacent_larger": "候选相邻更大尺寸",
        "adjacent_smaller": "候选相邻更小尺寸",
        "larger_cross": "候选跨档更大尺寸",
        "smaller_cross": "候选跨档更小尺寸",
    }.get(value, "尺寸待确认")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _avg_decimal(values: Iterable[Any]) -> Decimal:
    decimals = [_decimal(value) for value in values]
    if not decimals:
        return Decimal("0.0000")
    return _clamp_decimal(sum(decimals, Decimal("0")) / Decimal(len(decimals)))


def _clamp_decimal(value: Any) -> Decimal:
    decimal = _decimal(value)
    if decimal < 0:
        decimal = Decimal("0")
    if decimal > 1:
        decimal = Decimal("1")
    return _quantize(decimal)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _float(value: Any) -> float:
    return float(_decimal(value))


def _unique_evidence_ids(groups: Iterable[Iterable[Any] | Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        if group is None:
            continue
        values = group if isinstance(group, (list, tuple, set)) else (group,)
        for value in values:
            if value is None or value == "":
                continue
            normalized = str(value)
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


def _record_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash(parts, version=prefix).split(':')[-1][:48]}"
