"""M10 target-group inference service."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from app.services.core3_real_data.constants import (
    CORE3_M10_EVIDENCE_DOMAINS,
    CORE3_M10_FORBIDDEN_OUTPUT_FIELDS,
    CORE3_M10_RULE_VERSION,
    CORE3_M10_SEED_VERSION,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M08ProfileStatus,
    M10TargetGroupCandidateSource,
    M10TargetGroupCandidateStatus,
    M10TargetGroupEvidenceDomain,
    M10TargetGroupRelationLevel,
    M10TargetGroupReviewIssueType,
    M10TargetGroupSupportLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.target_group_repositories import M10InputBundle, M10TargetGroupRepository
from app.services.core3_real_data.target_group_schemas import (
    M10ServiceResult,
    M10SkuTargetGroupCandidateRecord,
    M10SkuTargetGroupEvidenceBreakdownRecord,
    M10SkuTargetGroupReviewIssueRecord,
    M10SkuTargetGroupScoreRecord,
    M10TargetGroupBuildResult,
    M10TargetGroupDomainEvidence,
)
from app.services.core3_real_data.target_group_seed_loader import M10TargetGroupSeed, M10TargetGroupSeedLoader


D0 = Decimal("0")
D1 = Decimal("1")


@dataclass(frozen=True)
class _TargetGroupScoreContext:
    bundle: M10InputBundle
    target_group: Mapping[str, Any]
    seed: M10TargetGroupSeed
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    rule_version: str


@dataclass(frozen=True)
class _RiskEvaluation:
    penalty: Decimal
    caps: tuple[dict[str, Any], ...]
    review_issues: tuple[dict[str, Any], ...]
    blocked_reason: str | None = None


class TargetGroupService:
    def __init__(self, repository: M10TargetGroupRepository, seed_loader: M10TargetGroupSeedLoader | None = None) -> None:
        self.repository = repository
        self.seed_loader = seed_loader or M10TargetGroupSeedLoader()

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M10_RULE_VERSION,
    ) -> M10ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        seed = self.seed_loader.load()
        input_bundles = self.repository.list_input_bundles(batch_id, sku_scope=sku_scope)

        build_results: list[M10TargetGroupBuildResult] = []
        for bundle in input_bundles:
            for target_group in seed.target_groups:
                build_results.append(
                    self._build_target_group(
                        _TargetGroupScoreContext(
                            bundle=bundle,
                            target_group=target_group,
                            seed=seed,
                            batch_id=batch_id,
                            run_id=run_id,
                            module_run_id=module_run_id,
                            rule_version=rule_version,
                        )
                    )
                )

        candidates = [item.candidate for item in build_results]
        scores = [item.score for item in build_results]
        breakdowns = [row for item in build_results for row in item.breakdowns]
        review_issues = [row for item in build_results for row in item.review_issues]
        for payload in [score.model_dump(mode="python") for score in scores]:
            _assert_no_forbidden_fields(payload)
        for payload in [candidate.model_dump(mode="python") for candidate in candidates]:
            _assert_no_forbidden_fields(payload)

        candidate_write = self.repository.save_candidates(candidates)
        score_write = self.repository.save_scores(scores)
        breakdown_write = self.repository.save_breakdowns(breakdowns)
        review_write = self.repository.save_review_issues(review_issues)

        relation_counts = Counter(score.relation_level for score in scores)
        candidate_counts = Counter(candidate.candidate_status for candidate in candidates)
        domain_counts = Counter(row.evidence_domain for row in breakdowns)
        warnings = _dedupe(
            [
                issue.issue_reason_cn
                for issue in review_issues
                if issue.issue_severity in {"warning", "blocking"}
            ]
        )[:50]
        status = Core3RunStatus.WARNING if warnings or review_issues else Core3RunStatus.SUCCESS
        created_count = (
            candidate_write.created_count
            + score_write.created_count
            + breakdown_write.created_count
            + review_write.created_count
        )
        summary = {
            "batch_id": batch_id,
            "rule_version": rule_version,
            "target_group_seed_version": seed.seed_version,
            "target_group_seed_file_version": seed.file_version,
            "target_group_seed_hash": seed.seed_hash,
            "target_group_seed_count": seed.target_group_count,
            "sku_count": len(input_bundles),
            "target_group_candidate_count": len(candidates),
            "target_group_score_count": len(scores),
            "target_group_evidence_breakdown_count": len(breakdowns),
            "target_group_review_issue_count": len(review_issues),
            "relation_level_counts": {str(key): value for key, value in relation_counts.items()},
            "candidate_status_counts": {str(key): value for key, value in candidate_counts.items()},
            "evidence_domain_counts": {str(key): value for key, value in domain_counts.items()},
            "created_output_count": created_count,
            "updated_output_count": (
                candidate_write.updated_count
                + score_write.updated_count
                + breakdown_write.updated_count
                + review_write.updated_count
            ),
            "reused_output_count": (
                candidate_write.reused_count
                + score_write.reused_count
                + breakdown_write.reused_count
                + review_write.reused_count
            ),
            "boundary_note": (
                "M10 只消费 M08 客群特征视图和 M09 用户任务分数推导目标客群，"
                "不生成价值战场、候选 SKU、核心竞品或高层报告。"
            ),
            "downstream_support": {
                "M11": "消费目标客群与用户任务共同推导价值战场",
                "M12": "消费目标客群辅助候选 SKU 召回",
                "M13": "消费客群匹配与证据拆分进行 pair 级评分",
                "M15": "消费客群业务原因和证据拆分解释竞品服务谁",
            },
        }
        return M10ServiceResult(
            candidates=candidates,
            scores=scores,
            breakdowns=breakdowns,
            review_issues=review_issues,
            summary=summary,
            warnings=warnings,
            status=status,
            input_count=len(input_bundles),
            output_count=len(candidates) + len(scores) + len(breakdowns) + len(review_issues),
            created_output_count=created_count,
        )

    def _build_target_group(self, context: _TargetGroupScoreContext) -> M10TargetGroupBuildResult:
        profile = context.bundle.profile
        view = context.bundle.feature_view
        group_code = str(context.target_group["target_group_code"])
        group_name = str(context.target_group["target_group_name"])
        group_definition = str(context.target_group["definition"])
        common = _common_output_fields(context)

        if view is None:
            return self._blocked_target_group(
                context,
                blocked_reason="缺少 M08 为 M10 准备的客群特征视图，不能推导目标客群。",
                issue_type=M10TargetGroupReviewIssueType.MISSING_FEATURE_VIEW.value,
            )
        if profile.profile_status in {M08ProfileStatus.INSUFFICIENT.value, M08ProfileStatus.BLOCKED.value}:
            return self._blocked_target_group(
                context,
                blocked_reason="M08 SKU 综合画像状态不足，不能生成目标客群判断。",
                issue_type=M10TargetGroupReviewIssueType.PROFILE_BLOCKED.value,
            )
        if not context.bundle.task_scores:
            return self._blocked_target_group(
                context,
                blocked_reason="缺少 M09 用户任务分数，不能跳过任务层直接生成目标客群。",
                issue_type=M10TargetGroupReviewIssueType.MISSING_TASK_SCORE.value,
            )

        payload = dict(view.feature_payload_json or {})
        domain_evidence = {
            M10TargetGroupEvidenceDomain.TASK: _score_task_domain(context.target_group, context.bundle),
            M10TargetGroupEvidenceDomain.COMMENT: _score_comment_domain(context.target_group, payload, context.bundle),
            M10TargetGroupEvidenceDomain.PRICE_CHANNEL: _score_price_channel_domain(context.target_group, payload, context.bundle),
            M10TargetGroupEvidenceDomain.MARKET: _score_market_domain(context.target_group, payload, context.bundle),
            M10TargetGroupEvidenceDomain.SERVICE: _score_service_domain(context.target_group, payload, context.bundle),
        }
        risk = _evaluate_risk(context, domain_evidence)
        task_score = domain_evidence[M10TargetGroupEvidenceDomain.TASK].score
        comment_score = domain_evidence[M10TargetGroupEvidenceDomain.COMMENT].score
        price_score = domain_evidence[M10TargetGroupEvidenceDomain.PRICE_CHANNEL].score
        market_score = domain_evidence[M10TargetGroupEvidenceDomain.MARKET].score
        service_score = domain_evidence[M10TargetGroupEvidenceDomain.SERVICE].score
        raw_score = _round4(
            task_score * Decimal("0.5500")
            + comment_score * Decimal("0.2000")
            + price_score * Decimal("0.1500")
            + market_score * Decimal("0.1000")
        )
        target_group_score = _clamp(raw_score - risk.penalty)
        for cap in risk.caps:
            max_score = _decimal(cap.get("max_score"))
            if target_group_score > max_score:
                target_group_score = max_score
        coverage = _domain_coverage_json(domain_evidence)
        relation_level = _relation_level(target_group_score, coverage, risk)
        candidate_status = _candidate_status(relation_level, risk, domain_evidence)
        confidence = _confidence(target_group_score, profile.confidence, coverage)
        confidence_level = _confidence_level(confidence)
        candidate_sources = _candidate_sources(domain_evidence)
        business_parts = {
            "购买任务": domain_evidence[M10TargetGroupEvidenceDomain.TASK].reason_cn,
            "用户线索": domain_evidence[M10TargetGroupEvidenceDomain.COMMENT].reason_cn,
            "价格渠道": domain_evidence[M10TargetGroupEvidenceDomain.PRICE_CHANNEL].reason_cn,
            "市场验证": domain_evidence[M10TargetGroupEvidenceDomain.MARKET].reason_cn,
            "服务侧面": domain_evidence[M10TargetGroupEvidenceDomain.SERVICE].reason_cn,
            "待复核点": "；".join(item["reason_cn"] for item in risk.review_issues) or "暂无阻断性问题",
        }
        business_reason = "；".join(f"{key}：{value}" for key, value in business_parts.items())
        input_fingerprint = stable_hash(
            {
                "profile_hash": profile.profile_hash,
                "feature_view_hash": view.view_hash,
                "task_score_fingerprint": context.bundle.task_score_fingerprint,
                "target_group_seed_hash": context.seed.seed_hash,
                "target_group_code": group_code,
                "rule_version": context.rule_version,
            },
            version="m10_target_group_input_v1",
        )
        candidate_id = _record_id("m10c", context.batch_id, profile.sku_code, group_code, context.seed.seed_hash)
        score_id = _record_id("m10s", context.batch_id, profile.sku_code, group_code, context.seed.seed_hash)
        source_tasks = _source_task_codes(context.target_group)
        evidence_ids = _dedupe([item for evidence in domain_evidence.values() for item in evidence.evidence_ids])[:100]
        matrix_refs = _dedupe([item.sku_signal_evidence_matrix_id for item in context.bundle.evidence_matrices])[:100]
        missing_signals = _missing_signals(domain_evidence)
        risk_flags = list(risk.review_issues)
        candidate_payload = {
            **common,
            "sku_target_group_candidate_id": candidate_id,
            "target_group_code": group_code,
            "target_group_name_cn": group_name,
            "target_group_definition_cn": group_definition,
            "candidate_source_json": candidate_sources,
            "candidate_source_count": len(candidate_sources),
            "source_task_codes_json": source_tasks,
            "candidate_initial_score": target_group_score,
            "candidate_reason_cn": _candidate_reason_cn(candidate_status, group_name, business_parts),
            "candidate_status": candidate_status,
            "reject_reason_json": {"reason_cn": "任务、评论、价格渠道与市场验证不足"} if candidate_status == M10TargetGroupCandidateStatus.REJECTED else {},
            "missing_signals_json": missing_signals,
            "risk_flags_json": risk_flags,
            "evidence_ids": evidence_ids,
            "evidence_matrix_refs_json": matrix_refs,
            "input_fingerprint": input_fingerprint,
            "result_hash": stable_hash(
                {"candidate_status": candidate_status, "score": target_group_score, "sources": candidate_sources},
                version="m10_candidate_result_v1",
            ),
            "processing_status": _processing_status(candidate_status, risk.review_issues),
            "review_required": bool(risk.review_issues),
            "review_status": "review_required" if risk.review_issues else "auto_pass",
            "review_reason_json": {"issues": list(risk.review_issues)},
        }
        score_payload = {
            **common,
            "sku_target_group_score_id": score_id,
            "sku_target_group_candidate_id": candidate_id,
            "target_group_code": group_code,
            "target_group_name_cn": group_name,
            "target_group_definition_cn": group_definition,
            "task_support_score": task_score,
            "comment_group_signal_score": comment_score,
            "price_channel_fit_score": price_score,
            "market_validation_score": market_score,
            "service_side_score": service_score,
            "raw_target_group_score": raw_score,
            "risk_penalty": risk.penalty,
            "target_group_score": target_group_score,
            "relation_level": relation_level,
            "relation_reason_json": _relation_reason_json(relation_level, coverage, risk),
            "confidence": confidence,
            "confidence_level": confidence_level,
            "evidence_domain_count": int(coverage["positive_domain_count"]),
            "effective_domain_json": coverage,
            "source_task_scores_json": _source_task_scores(context.target_group, context.bundle),
            "score_breakdown_json": {
                "task": float(task_score),
                "comment": float(comment_score),
                "price_channel": float(price_score),
                "market": float(market_score),
                "service_side": float(service_score),
                "formula": "task*0.55 + comment*0.20 + price_channel*0.15 + market*0.10; service_side only as side evidence",
            },
            "cap_rule_applied_json": list(risk.caps),
            "missing_signals_json": missing_signals,
            "risk_flags_json": risk_flags,
            "business_reason_cn": business_reason,
            "business_reason_parts_json": business_parts,
            "evidence_ids": evidence_ids,
            "evidence_matrix_refs_json": matrix_refs,
            "input_fingerprint": input_fingerprint,
            "result_hash": stable_hash(
                {
                    "target_group_code": group_code,
                    "target_group_score": target_group_score,
                    "relation_level": relation_level,
                    "confidence": confidence,
                    "business_parts": business_parts,
                },
                version="m10_score_result_v1",
            ),
            "processing_status": _processing_status(candidate_status, risk.review_issues),
            "review_required": bool(risk.review_issues),
            "review_status": "review_required" if risk.review_issues else "auto_pass",
            "review_reason_json": {"issues": list(risk.review_issues)},
        }
        breakdowns = _breakdown_records(
            context=context,
            score_id=score_id,
            group_name=group_name,
            domain_evidence=domain_evidence,
            risk=risk,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        review_issues = _review_issue_records(
            context=context,
            candidate_id=candidate_id,
            score_id=score_id,
            group_name=group_name,
            issues=risk.review_issues,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        return M10TargetGroupBuildResult(
            candidate=M10SkuTargetGroupCandidateRecord(**candidate_payload),
            score=M10SkuTargetGroupScoreRecord(**score_payload),
            breakdowns=breakdowns,
            review_issues=review_issues,
        )

    def _blocked_target_group(
        self,
        context: _TargetGroupScoreContext,
        *,
        blocked_reason: str,
        issue_type: str,
    ) -> M10TargetGroupBuildResult:
        group_code = str(context.target_group["target_group_code"])
        group_name = str(context.target_group["target_group_name"])
        group_definition = str(context.target_group["definition"])
        common = _common_output_fields(context)
        input_fingerprint = stable_hash(
            {
                "profile_hash": context.bundle.profile.profile_hash,
                "feature_view_hash": _feature_view_hash(context.bundle),
                "task_score_fingerprint": context.bundle.task_score_fingerprint,
                "target_group_seed_hash": context.seed.seed_hash,
                "target_group_code": group_code,
                "blocked": blocked_reason,
            },
            version="m10_target_group_input_v1",
        )
        candidate_id = _record_id("m10c", context.batch_id, context.bundle.profile.sku_code, group_code, context.seed.seed_hash)
        score_id = _record_id("m10s", context.batch_id, context.bundle.profile.sku_code, group_code, context.seed.seed_hash)
        issue = {
            "issue_type": issue_type,
            "reason_cn": blocked_reason,
            "severity": "blocking",
            "suggestion_cn": "先补齐 M08 客群特征视图或 M09 用户任务结果，再重新运行 M10。",
        }
        candidate = M10SkuTargetGroupCandidateRecord(
            **{
                **common,
                "sku_target_group_candidate_id": candidate_id,
                "target_group_code": group_code,
                "target_group_name_cn": group_name,
                "target_group_definition_cn": group_definition,
                "candidate_status": M10TargetGroupCandidateStatus.BLOCKED,
                "candidate_source_json": [],
                "candidate_source_count": 0,
                "source_task_codes_json": _source_task_codes(context.target_group),
                "candidate_initial_score": D0,
                "candidate_reason_cn": blocked_reason,
                "missing_signals_json": [{"domain": "upstream", "reason_cn": blocked_reason}],
                "risk_flags_json": [issue],
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(issue, version="m10_candidate_result_v1"),
                "processing_status": "blocked",
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {"issues": [issue]},
            }
        )
        score = M10SkuTargetGroupScoreRecord(
            **{
                **common,
                "sku_target_group_score_id": score_id,
                "sku_target_group_candidate_id": candidate_id,
                "target_group_code": group_code,
                "target_group_name_cn": group_name,
                "target_group_definition_cn": group_definition,
                "relation_level": M10TargetGroupRelationLevel.BLOCKED,
                "confidence_level": Core3ConfidenceLevel.UNKNOWN,
                "business_reason_cn": blocked_reason,
                "business_reason_parts_json": {"待复核点": blocked_reason},
                "missing_signals_json": [{"domain": "upstream", "reason_cn": blocked_reason}],
                "risk_flags_json": [issue],
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(issue, version="m10_score_result_v1"),
                "processing_status": "blocked",
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {"issues": [issue]},
            }
        )
        empty_domains = {
            domain: M10TargetGroupDomainEvidence(
                domain=domain,
                support_level=M10TargetGroupSupportLevel.MISSING,
                score=D0,
                weight=_domain_weight(domain),
                reason_cn=blocked_reason if domain == M10TargetGroupEvidenceDomain.RISK else "上游输入不足，暂无法判断。",
            )
            for domain in (
                M10TargetGroupEvidenceDomain.TASK,
                M10TargetGroupEvidenceDomain.COMMENT,
                M10TargetGroupEvidenceDomain.PRICE_CHANNEL,
                M10TargetGroupEvidenceDomain.MARKET,
                M10TargetGroupEvidenceDomain.SERVICE,
            )
        }
        risk = _RiskEvaluation(
            penalty=Decimal("1.0000"),
            caps=({"rule": "blocked_input", "max_score": "0.0000", "reason_cn": blocked_reason},),
            review_issues=(issue,),
            blocked_reason=blocked_reason,
        )
        breakdowns = _breakdown_records(
            context=context,
            score_id=score_id,
            group_name=group_name,
            domain_evidence=empty_domains,
            risk=risk,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        review_issues = _review_issue_records(
            context=context,
            candidate_id=candidate_id,
            score_id=score_id,
            group_name=group_name,
            issues=(issue,),
            common=common,
            input_fingerprint=input_fingerprint,
        )
        return M10TargetGroupBuildResult(candidate=candidate, score=score, breakdowns=breakdowns, review_issues=review_issues)


def _score_task_domain(group: Mapping[str, Any], bundle: M10InputBundle) -> M10TargetGroupDomainEvidence:
    source_codes = _source_task_codes(group)
    scores_by_code = {row.task_code: row for row in bundle.task_scores}
    matched: list[dict[str, Any]] = []
    values: list[Decimal] = []
    for task_code in source_codes:
        row = scores_by_code.get(task_code)
        if row is None:
            continue
        task_value = _clamp(_decimal(row.task_score) * _task_relation_factor(str(row.relation_level)))
        matched.append(
            {
                "task_code": task_code,
                "task_name_cn": row.task_name_cn,
                "relation_level": row.relation_level,
                "task_score": float(row.task_score or 0),
                "weighted_support": float(task_value),
                "review_required": bool(row.review_required),
            }
        )
        values.append(task_value)
    if not values:
        return M10TargetGroupDomainEvidence(
            domain=M10TargetGroupEvidenceDomain.TASK,
            support_level=M10TargetGroupSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M10TargetGroupEvidenceDomain.TASK),
            reason_cn="源用户任务未形成可用强弱关系，不能支撑客群判断。",
            source_feature_refs=[{"feature": "M09.task_scores", "expected": source_codes}],
        )
    score = _round4(sum(values) / Decimal(len(source_codes)))
    reason = f"源用户任务命中 {len(matched)} 项，主要任务为 {', '.join(item['task_name_cn'] or item['task_code'] for item in matched[:3])}。"
    return M10TargetGroupDomainEvidence(
        domain=M10TargetGroupEvidenceDomain.TASK,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M10TargetGroupEvidenceDomain.TASK),
        reason_cn=reason,
        evidence_ids=_task_evidence_ids(bundle, source_codes),
        source_feature_refs=matched,
        risk_json={"source_task_count": len(source_codes), "matched_task_count": len(matched)},
    )


def _score_comment_domain(group: Mapping[str, Any], payload: Mapping[str, Any], bundle: M10InputBundle) -> M10TargetGroupDomainEvidence:
    comment_summary = dict(payload.get("comment_signal_summary") or {})
    type_summary = dict(comment_summary.get("signal_type_summary") or {})
    cue_summary = dict(type_summary.get("target_group_cue") or {})
    pain_summary = dict(type_summary.get("pain_point") or {})
    group_code = str(group.get("target_group_code") or "")
    target_hints = [str(item) for item in cue_summary.get("target_code_hints") or []]
    top_phrases = [str(item) for item in cue_summary.get("top_phrases") or []]
    pain_phrases = [str(item) for item in pain_summary.get("top_phrases") or []]
    keyword_hit = _keyword_hit(group, [*top_phrases, *pain_phrases])
    if group_code not in target_hints and not keyword_hit:
        return M10TargetGroupDomainEvidence(
            domain=M10TargetGroupEvidenceDomain.COMMENT,
            support_level=M10TargetGroupSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M10TargetGroupEvidenceDomain.COMMENT),
            reason_cn="评论中暂未形成该客群的稳定人群线索。",
            source_feature_refs=[{"feature": "comment_signal_summary.target_group_cue", "target_code_hints": target_hints[:12]}],
        )
    strong_count = int(cue_summary.get("strong_count") or 0)
    medium_count = int(cue_summary.get("medium_count") or 0)
    signal_count = int(cue_summary.get("signal_count") or 0)
    score = Decimal("0.9000") if strong_count else Decimal("0.7000")
    if keyword_hit and group_code not in target_hints:
        score = Decimal("0.4500")
    if signal_count <= 1:
        score = min(score, Decimal("0.5500"))
    reason = f"评论出现该客群线索，强信号 {strong_count} 条、中信号 {medium_count} 条。"
    return M10TargetGroupDomainEvidence(
        domain=M10TargetGroupEvidenceDomain.COMMENT,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M10TargetGroupEvidenceDomain.COMMENT),
        reason_cn=reason,
        evidence_ids=_matrix_evidence_ids(bundle, "comment", ("target_group_cue", "pain_point")),
        source_feature_refs=[
            {
                "feature": "comment_signal_summary.target_group_cue",
                "target_code_hints": target_hints[:12],
                "top_phrases": top_phrases[:8],
                "pain_phrases": pain_phrases[:8],
            }
        ],
        risk_json={"signal_count": signal_count},
    )


def _score_price_channel_domain(group: Mapping[str, Any], payload: Mapping[str, Any], bundle: M10InputBundle) -> M10TargetGroupDomainEvidence:
    market_summary = dict(payload.get("market_summary") or {})
    group_code = str(group.get("target_group_code") or "")
    screen_size = _decimal(market_summary.get("screen_size_inch"))
    price_band = str(market_summary.get("price_band_category") or market_summary.get("price_band_size") or "")
    platform = str(market_summary.get("main_platform") or market_summary.get("platform") or "")
    score = D0
    reasons: list[str] = []
    if group_code in {"TG_FAMILY_UPGRADE", "TG_NEW_HOME_DECORATOR"}:
        if screen_size >= Decimal("75"):
            score = Decimal("0.8500") if screen_size >= Decimal("85") else Decimal("0.7000")
            reasons.append(f"{int(screen_size)} 英寸大屏适合客厅换新或新家配置")
    elif group_code == "TG_AV_QUALITY_SEEKER":
        if price_band in {"mid_high", "high"}:
            score = Decimal("0.7500")
            reasons.append(f"价位处于{_price_band_cn(price_band)}，与影音升级客群匹配")
    elif group_code in {"TG_GAMER", "TG_SPORTS_FAN"}:
        if price_band in {"mid", "mid_high", "high"}:
            score = Decimal("0.6500")
            reasons.append(f"价位处于{_price_band_cn(price_band)}，可承载游戏体育配置诉求")
    elif group_code == "TG_VALUE_BUYER":
        if price_band in {"low", "mid_low", "mid"}:
            score = Decimal("0.7800")
            reasons.append(f"价位处于{_price_band_cn(price_band)}，符合性价比决策")
        elif price_band in {"mid_high", "high"}:
            score = Decimal("0.2000")
            reasons.append(f"价位处于{_price_band_cn(price_band)}，与性价比客群存在错位")
    elif group_code == "TG_BEDROOM_SECOND_TV":
        if screen_size <= Decimal("65") and price_band in {"low", "mid_low", "mid"}:
            score = Decimal("0.8500")
            reasons.append("尺寸和价位更接近卧室副屏")
        elif screen_size >= Decimal("75"):
            score = Decimal("0.1000")
            reasons.append(f"{int(screen_size)} 英寸更偏客厅主屏，不适合作为卧室副屏主判断")
    elif group_code in {"TG_SENIOR_FAMILY", "TG_CHILD_FAMILY"}:
        if price_band in {"low", "mid_low", "mid"}:
            score = Decimal("0.5600")
            reasons.append(f"价位处于{_price_band_cn(price_band)}，家庭普及型购买门槛较低")
    if score == D0 and (price_band or screen_size > 0 or platform):
        score = Decimal("0.3000")
        reasons.append("已有价格渠道信息，但与该客群的匹配度较弱")
    if score == D0:
        return M10TargetGroupDomainEvidence(
            domain=M10TargetGroupEvidenceDomain.PRICE_CHANNEL,
            support_level=M10TargetGroupSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M10TargetGroupEvidenceDomain.PRICE_CHANNEL),
            reason_cn="缺少可判断客群价格或渠道匹配的市场信息。",
            source_feature_refs=[{"feature": "market_summary", "group_code": group_code}],
        )
    return M10TargetGroupDomainEvidence(
        domain=M10TargetGroupEvidenceDomain.PRICE_CHANNEL,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M10TargetGroupEvidenceDomain.PRICE_CHANNEL),
        reason_cn="；".join(reasons),
        evidence_ids=_matrix_evidence_ids(bundle, "market", ("price", "platform")),
        source_feature_refs=[{"feature": "market_summary", "screen_size_inch": float(screen_size), "price_band": price_band, "platform": platform}],
        risk_json={"price_mismatch": _price_mismatch(group_code, screen_size, price_band)},
    )


def _score_market_domain(group: Mapping[str, Any], payload: Mapping[str, Any], bundle: M10InputBundle) -> M10TargetGroupDomainEvidence:
    market_summary = dict(payload.get("market_summary") or {})
    pool_summary = dict(payload.get("pool_summary") or {})
    group_code = str(group.get("target_group_code") or "")
    screen_size = _decimal(market_summary.get("screen_size_inch"))
    price_band = str(market_summary.get("price_band_category") or market_summary.get("price_band_size") or "")
    volume = _decimal(market_summary.get("sales_volume_total"))
    amount = _decimal(market_summary.get("sales_amount_total"))
    sample_status = str(market_summary.get("sample_status") or pool_summary.get("sample_status") or "")
    scores: list[Decimal] = []
    reasons: list[str] = []
    if group_code in {"TG_FAMILY_UPGRADE", "TG_NEW_HOME_DECORATOR"} and screen_size >= Decimal("75") and (volume > 0 or amount > 0):
        scores.append(Decimal("0.7500"))
        reasons.append("大屏且已有销量/销售额，说明具备家庭配置市场基础")
    if group_code == "TG_AV_QUALITY_SEEKER" and price_band in {"mid_high", "high"} and amount > 0:
        scores.append(Decimal("0.7000"))
        reasons.append("中高价位仍有销售额支撑，说明影音升级有市场接受度")
    if group_code in {"TG_GAMER", "TG_SPORTS_FAN"} and screen_size >= Decimal("75") and (volume > 0 or amount > 0):
        scores.append(Decimal("0.6200"))
        reasons.append("大屏销售数据可辅助验证游戏体育场景")
    if group_code == "TG_VALUE_BUYER" and volume > 0 and price_band in {"low", "mid_low", "mid"}:
        scores.append(Decimal("0.7000"))
        reasons.append("主流价位且有销量，支撑性价比购买客群")
    if group_code == "TG_BEDROOM_SECOND_TV":
        if screen_size <= Decimal("65"):
            scores.append(Decimal("0.6500"))
            reasons.append("尺寸更符合卧室副屏市场使用")
        elif screen_size >= Decimal("75"):
            scores.append(Decimal("0.1500"))
            reasons.append("大屏市场定位与卧室副屏不一致")
    if group_code in {"TG_SENIOR_FAMILY", "TG_CHILD_FAMILY"} and (volume > 0 or amount > 0):
        scores.append(Decimal("0.4500"))
        reasons.append("销量/销售额可作为家庭客群辅助验证")
    pool_count = int(pool_summary.get("pool_count") or 0)
    if pool_count > 0 and scores:
        scores.append(Decimal("0.5500"))
        reasons.append(f"存在 {pool_count} 个市场对照池，可辅助判断定位")
    if not scores and (volume > 0 or amount > 0):
        scores.append(Decimal("0.3000"))
        reasons.append("已有市场数据，但与该客群映射较弱")
    if not scores:
        return M10TargetGroupDomainEvidence(
            domain=M10TargetGroupEvidenceDomain.MARKET,
            support_level=M10TargetGroupSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M10TargetGroupEvidenceDomain.MARKET),
            reason_cn="缺少足够的销量、销售额或对照池来验证该客群。",
            source_feature_refs=[{"feature": "market_summary", "group_code": group_code}],
            risk_json={"sample_status": sample_status},
        )
    score = _round4(sum(scores) / Decimal(len(scores)))
    return M10TargetGroupDomainEvidence(
        domain=M10TargetGroupEvidenceDomain.MARKET,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M10TargetGroupEvidenceDomain.MARKET),
        reason_cn="；".join(reasons),
        evidence_ids=_matrix_evidence_ids(bundle, "market", ("sales", "trend")) + _matrix_evidence_ids(bundle, "pool", ("same_size", "same_price_band")),
        source_feature_refs=[{"feature": "market_summary", "price_band": price_band, "sales_volume_total": float(volume), "sales_amount_total": float(amount), "pool_count": pool_count}],
        risk_json={"sample_status": sample_status, "quality_flags": market_summary.get("quality_flags") or []},
    )


def _score_service_domain(group: Mapping[str, Any], payload: Mapping[str, Any], bundle: M10InputBundle) -> M10TargetGroupDomainEvidence:
    comment_summary = dict(payload.get("comment_signal_summary") or {})
    type_summary = dict(comment_summary.get("signal_type_summary") or {})
    service_summary = dict(type_summary.get("service_signal") or {})
    signal_count = int(service_summary.get("signal_count") or 0)
    strong_count = int(service_summary.get("strong_count") or 0)
    group_code = str(group.get("target_group_code") or "")
    if signal_count <= 0:
        return M10TargetGroupDomainEvidence(
            domain=M10TargetGroupEvidenceDomain.SERVICE,
            support_level=M10TargetGroupSupportLevel.NOT_APPLICABLE,
            score=D0,
            weight=_domain_weight(M10TargetGroupEvidenceDomain.SERVICE),
            reason_cn="服务体验暂无稳定客群侧面线索。",
            source_feature_refs=[{"feature": "comment_signal_summary.service_signal"}],
        )
    score = Decimal("0.6000") if strong_count else Decimal("0.4500")
    if group_code != "TG_NEW_HOME_DECORATOR":
        score = min(score, Decimal("0.3000"))
    reason = f"服务/安装相关评论 {signal_count} 条，可作为新家装修或服务敏感人群的侧面参考。"
    return M10TargetGroupDomainEvidence(
        domain=M10TargetGroupEvidenceDomain.SERVICE,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M10TargetGroupEvidenceDomain.SERVICE),
        reason_cn=reason,
        evidence_ids=_matrix_evidence_ids(bundle, "comment", ("service_signal",)),
        source_feature_refs=[{"feature": "comment_signal_summary.service_signal", "signal_count": signal_count, "strong_count": strong_count}],
        risk_json={"service_side_only": True},
    )


def _evaluate_risk(
    context: _TargetGroupScoreContext,
    domain_evidence: Mapping[M10TargetGroupEvidenceDomain, M10TargetGroupDomainEvidence],
) -> _RiskEvaluation:
    issues: list[dict[str, Any]] = []
    caps: list[dict[str, Any]] = []
    penalty = D0
    positive_domains = [
        domain
        for domain, evidence in domain_evidence.items()
        if domain != M10TargetGroupEvidenceDomain.SERVICE and evidence.score >= Decimal("0.2500")
    ]
    if positive_domains == [M10TargetGroupEvidenceDomain.COMMENT]:
        caps.append({"rule": "only_comment", "max_score": "0.4900", "reason_cn": "评论单域只能形成弱客群线索。"})
        issues.append(_issue(M10TargetGroupReviewIssueType.ONLY_COMMENT, "该客群主要来自评论线索，缺少任务、价格渠道或市场验证。"))
    if not positive_domains and domain_evidence[M10TargetGroupEvidenceDomain.SERVICE].score >= Decimal("0.2500"):
        caps.append({"rule": "only_service", "max_score": "0.4900", "reason_cn": "服务单域只能作为客群侧面证据。"})
        issues.append(_issue(M10TargetGroupReviewIssueType.ONLY_SERVICE, "该客群主要来自服务体验线索，不能直接形成主客群判断。"))
    price_risk = domain_evidence[M10TargetGroupEvidenceDomain.PRICE_CHANNEL].risk_json
    if price_risk.get("price_mismatch"):
        caps.append({"rule": "price_mismatch", "max_score": "0.4900", "reason_cn": "价格/尺寸与客群定义存在错位。"})
        issues.append(_issue(M10TargetGroupReviewIssueType.PRICE_MISMATCH, "价格或尺寸与该客群定义不一致，需要业务复核。"))
    market_risk = domain_evidence[M10TargetGroupEvidenceDomain.MARKET].risk_json
    if market_risk.get("sample_status") in {"limited", "insufficient"}:
        penalty += Decimal("0.0300")
        issues.append(_issue(M10TargetGroupReviewIssueType.MARKET_LIMITED, "市场样本有限，客群判断需要带限制说明。"))
    source_task_codes = set(_source_task_codes(context.target_group))
    inherited_reviews = [
        row
        for row in context.bundle.task_review_issues
        if row.task_code in source_task_codes and str(row.issue_severity) in {"warning", "blocking", "error", "high", "medium"}
    ]
    if inherited_reviews:
        caps.append({"rule": "task_review_inherited", "max_score": "0.7400", "reason_cn": "源用户任务存在复核问题，客群不能直接升为主客群。"})
        issues.append(_issue(M10TargetGroupReviewIssueType.TASK_REVIEW_INHERITED, "源用户任务存在复核问题，客群结论需继承降级。"))
    if (
        domain_evidence[M10TargetGroupEvidenceDomain.TASK].score < Decimal("0.2500")
        and domain_evidence[M10TargetGroupEvidenceDomain.COMMENT].score >= Decimal("0.7000")
        and domain_evidence[M10TargetGroupEvidenceDomain.MARKET].score >= Decimal("0.6500")
    ):
        issues.append(_issue(M10TargetGroupReviewIssueType.TASK_CONFLICT, "评论和市场有线索，但源用户任务支撑不足，需复核是否错配。"))
    return _RiskEvaluation(penalty=_clamp(penalty), caps=tuple(caps), review_issues=tuple(_dedupe_issue_dicts(issues)))


def _breakdown_records(
    *,
    context: _TargetGroupScoreContext,
    score_id: str,
    group_name: str,
    domain_evidence: Mapping[M10TargetGroupEvidenceDomain, M10TargetGroupDomainEvidence],
    risk: _RiskEvaluation,
    common: Mapping[str, Any],
    input_fingerprint: str,
) -> list[M10SkuTargetGroupEvidenceBreakdownRecord]:
    records: list[M10SkuTargetGroupEvidenceBreakdownRecord] = []
    breakdown_common = _without_profile_view_refs(common)
    for domain in CORE3_M10_EVIDENCE_DOMAINS:
        if domain in domain_evidence:
            evidence = domain_evidence[domain]
        elif domain == M10TargetGroupEvidenceDomain.RISK:
            evidence = M10TargetGroupDomainEvidence(
                domain=domain,
                support_level=M10TargetGroupSupportLevel.CONFLICT if risk.review_issues else M10TargetGroupSupportLevel.NOT_APPLICABLE,
                score=risk.penalty,
                weight=D0,
                reason_cn="；".join(item["reason_cn"] for item in risk.review_issues) or "未发现需要封顶或降级的风险。",
                risk_json={"caps": list(risk.caps), "issues": list(risk.review_issues)},
            )
        elif domain == M10TargetGroupEvidenceDomain.SEED:
            evidence = M10TargetGroupDomainEvidence(
                domain=domain,
                support_level=M10TargetGroupSupportLevel.STRONG,
                score=D1,
                weight=D0,
                reason_cn="目标客群本体来自固定 TV MVP seed，当前只作为推导框架，不直接代表 SKU 结论。",
                source_feature_refs=[{"target_group_seed_version": context.seed.seed_version, "target_group_seed_hash": context.seed.seed_hash}],
            )
        else:
            profile = context.bundle.profile
            evidence = M10TargetGroupDomainEvidence(
                domain=domain,
                support_level=_support_level(_decimal(profile.confidence)),
                score=_clamp(_decimal(profile.confidence)),
                weight=D0,
                reason_cn=f"M08 综合画像完整度 {float(profile.data_completeness_score or 0):.2f}，作为客群判断底层可信度参考。",
                evidence_ids=list(profile.representative_evidence_ids or [])[:20],
                source_feature_refs=[{"profile_hash": profile.profile_hash, "profile_status": profile.profile_status}],
            )
        weighted = _round4(evidence.score * evidence.weight)
        group_code = str(context.target_group["target_group_code"])
        payload = {
            "sku_code": context.bundle.profile.sku_code,
            "target_group_code": group_code,
            "domain": domain.value,
            "score": evidence.score,
            "weight": evidence.weight,
            "input_fingerprint": input_fingerprint,
        }
        records.append(
            M10SkuTargetGroupEvidenceBreakdownRecord(
                **{
                    **breakdown_common,
                    "sku_target_group_evidence_breakdown_id": _record_id(
                        "m10b",
                        context.batch_id,
                        context.bundle.profile.sku_code,
                        group_code,
                        domain.value,
                        context.seed.seed_hash,
                    ),
                    "sku_target_group_score_id": score_id,
                    "target_group_code": group_code,
                    "target_group_name_cn": group_name,
                    "evidence_domain": domain,
                    "support_level": evidence.support_level,
                    "domain_score": evidence.score,
                    "domain_weight": evidence.weight,
                    "weighted_score": weighted,
                    "evidence_count": len(evidence.evidence_ids),
                    "evidence_ids": evidence.evidence_ids[:100],
                    "source_feature_refs_json": evidence.source_feature_refs,
                    "domain_reason_cn": evidence.reason_cn,
                    "domain_risk_json": evidence.risk_json,
                    "input_fingerprint": input_fingerprint,
                    "result_hash": stable_hash(payload, version="m10_breakdown_result_v1"),
                    "review_required": domain == M10TargetGroupEvidenceDomain.RISK and bool(risk.review_issues),
                    "review_status": "review_required" if domain == M10TargetGroupEvidenceDomain.RISK and risk.review_issues else "auto_pass",
                    "review_reason_json": {"issues": list(risk.review_issues)} if domain == M10TargetGroupEvidenceDomain.RISK else {},
                }
            )
        )
    return records


def _review_issue_records(
    *,
    context: _TargetGroupScoreContext,
    candidate_id: str,
    score_id: str,
    group_name: str,
    issues: Sequence[Mapping[str, Any]],
    common: Mapping[str, Any],
    input_fingerprint: str,
) -> list[M10SkuTargetGroupReviewIssueRecord]:
    records: list[M10SkuTargetGroupReviewIssueRecord] = []
    issue_common = _without_profile_view_refs(common)
    group_code = str(context.target_group["target_group_code"])
    for issue in issues:
        issue_type = str(issue.get("issue_type") or M10TargetGroupReviewIssueType.SEED_GAP.value)
        payload = {
            "sku_code": context.bundle.profile.sku_code,
            "target_group_code": group_code,
            "issue_type": issue_type,
            "input_fingerprint": input_fingerprint,
        }
        records.append(
            M10SkuTargetGroupReviewIssueRecord(
                **{
                    **issue_common,
                    "sku_target_group_review_issue_id": _record_id(
                        "m10r",
                        context.batch_id,
                        context.bundle.profile.sku_code,
                        group_code,
                        issue_type,
                        context.seed.seed_hash,
                    ),
                    "sku_target_group_score_id": score_id,
                    "sku_target_group_candidate_id": candidate_id,
                    "target_group_code": group_code,
                    "target_group_name_cn": group_name,
                    "issue_type": issue_type,
                    "issue_severity": str(issue.get("severity") or "warning"),
                    "issue_status": "open",
                    "issue_reason_cn": str(issue.get("reason_cn") or "目标客群证据需要复核。"),
                    "issue_detail_json": dict(issue),
                    "affected_output_json": {"score_id": score_id, "candidate_id": candidate_id},
                    "evidence_ids": [],
                    "suggested_action_cn": str(issue.get("suggestion_cn") or "补充上游数据或人工复核后重新运行 M10。"),
                    "input_fingerprint": input_fingerprint,
                    "result_hash": stable_hash(payload, version="m10_review_issue_result_v1"),
                    "processing_status": "blocked" if issue.get("severity") == "blocking" else "warning",
                    "review_required": True,
                    "review_status": "review_required",
                    "review_reason_json": dict(issue),
                }
            )
        )
    return records


def _common_output_fields(context: _TargetGroupScoreContext) -> dict[str, Any]:
    profile = context.bundle.profile
    view = context.bundle.feature_view
    return {
        "project_id": profile.project_id,
        "category_code": profile.category_code,
        "batch_id": context.batch_id,
        "run_id": context.run_id,
        "module_run_id": context.module_run_id,
        "sku_signal_profile_id": profile.sku_signal_profile_id,
        "sku_downstream_feature_view_id": view.sku_downstream_feature_view_id if view else None,
        "sku_code": profile.sku_code,
        "model_code": (profile.sku_master_json or {}).get("model_code"),
        "model_name": profile.model_name,
        "brand_name": profile.brand_name,
        "rule_version": context.rule_version,
        "target_group_seed_version": CORE3_M10_SEED_VERSION,
        "target_group_seed_file_version": context.seed.file_version,
        "target_group_seed_hash": context.seed.seed_hash,
        "profile_hash": profile.profile_hash,
        "feature_view_hash": _feature_view_hash(context.bundle),
        "task_score_fingerprint": context.bundle.task_score_fingerprint,
    }


def _without_profile_view_refs(common: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in common.items()
        if key not in {"sku_signal_profile_id", "sku_downstream_feature_view_id"}
    }


def _source_task_codes(group: Mapping[str, Any]) -> list[str]:
    return [str(code) for code in group.get("source_task_codes") or group.get("mapped_task_codes") or []]


def _source_task_scores(group: Mapping[str, Any], bundle: M10InputBundle) -> list[dict[str, Any]]:
    source_codes = set(_source_task_codes(group))
    return [
        {
            "task_code": row.task_code,
            "task_name_cn": row.task_name_cn,
            "relation_level": row.relation_level,
            "task_score": float(row.task_score or 0),
            "confidence": float(row.confidence or 0),
            "review_required": bool(row.review_required),
        }
        for row in bundle.task_scores
        if row.task_code in source_codes
    ]


def _task_evidence_ids(bundle: M10InputBundle, source_task_codes: Sequence[str]) -> list[str]:
    source_codes = set(source_task_codes)
    ids: list[str] = []
    for row in bundle.task_breakdowns:
        if row.task_code in source_codes:
            ids.extend(str(item) for item in row.evidence_refs_json or [])
    return _dedupe(ids)[:100]


def _matrix_evidence_ids(bundle: M10InputBundle, domain: str, sub_domains: Sequence[str] = ()) -> list[str]:
    sub_domain_set = set(sub_domains)
    ids: list[str] = []
    for matrix in bundle.evidence_matrices:
        if matrix.domain != domain:
            continue
        if sub_domain_set and matrix.sub_domain not in sub_domain_set:
            continue
        ids.extend(str(item) for item in matrix.representative_evidence_ids or [])
    return _dedupe(ids)[:100]


def _domain_weight(domain: M10TargetGroupEvidenceDomain) -> Decimal:
    return {
        M10TargetGroupEvidenceDomain.TASK: Decimal("0.5500"),
        M10TargetGroupEvidenceDomain.COMMENT: Decimal("0.2000"),
        M10TargetGroupEvidenceDomain.PRICE_CHANNEL: Decimal("0.1500"),
        M10TargetGroupEvidenceDomain.MARKET: Decimal("0.1000"),
        M10TargetGroupEvidenceDomain.SERVICE: Decimal("0.0000"),
    }.get(domain, D0)


def _task_relation_factor(relation_level: str) -> Decimal:
    return {
        "main": Decimal("1.0000"),
        "secondary": Decimal("0.7500"),
        "weak": Decimal("0.4500"),
        "insufficient": Decimal("0.0000"),
        "blocked": Decimal("0.0000"),
    }.get(relation_level, D0)


def _relation_level(score: Decimal, coverage: Mapping[str, Any], risk: _RiskEvaluation) -> M10TargetGroupRelationLevel:
    if risk.blocked_reason:
        return M10TargetGroupRelationLevel.BLOCKED
    positive_domains = set(coverage.get("positive_domains") or [])
    has_task_or_market = M10TargetGroupEvidenceDomain.TASK.value in positive_domains or M10TargetGroupEvidenceDomain.MARKET.value in positive_domains
    if score >= Decimal("0.7500") and len(positive_domains) >= 2 and has_task_or_market:
        return M10TargetGroupRelationLevel.MAIN
    if score >= Decimal("0.6000") and (len(positive_domains) >= 2 or M10TargetGroupEvidenceDomain.TASK.value in positive_domains):
        return M10TargetGroupRelationLevel.SECONDARY
    if score >= Decimal("0.4000"):
        return M10TargetGroupRelationLevel.WEAK
    return M10TargetGroupRelationLevel.INSUFFICIENT


def _candidate_status(
    relation_level: M10TargetGroupRelationLevel,
    risk: _RiskEvaluation,
    domain_evidence: Mapping[M10TargetGroupEvidenceDomain, M10TargetGroupDomainEvidence],
) -> M10TargetGroupCandidateStatus:
    if relation_level == M10TargetGroupRelationLevel.BLOCKED:
        return M10TargetGroupCandidateStatus.BLOCKED
    if relation_level == M10TargetGroupRelationLevel.INSUFFICIENT and not any(item.score > 0 for item in domain_evidence.values()):
        return M10TargetGroupCandidateStatus.REJECTED
    if risk.review_issues:
        return M10TargetGroupCandidateStatus.REVIEW_REQUIRED
    return M10TargetGroupCandidateStatus.ACTIVE


def _candidate_sources(domain_evidence: Mapping[M10TargetGroupEvidenceDomain, M10TargetGroupDomainEvidence]) -> list[str]:
    result: list[str] = []
    if domain_evidence[M10TargetGroupEvidenceDomain.TASK].score > 0:
        result.append(M10TargetGroupCandidateSource.TASK.value)
    if domain_evidence[M10TargetGroupEvidenceDomain.COMMENT].score > 0:
        result.append(M10TargetGroupCandidateSource.COMMENT.value)
    if domain_evidence[M10TargetGroupEvidenceDomain.PRICE_CHANNEL].score > 0:
        result.append(M10TargetGroupCandidateSource.PRICE_CHANNEL.value)
    if domain_evidence[M10TargetGroupEvidenceDomain.MARKET].score > 0:
        result.append(M10TargetGroupCandidateSource.MARKET.value)
    if domain_evidence[M10TargetGroupEvidenceDomain.SERVICE].score > 0:
        result.append(M10TargetGroupCandidateSource.SERVICE.value)
    return _dedupe(result)


def _domain_coverage_json(domain_evidence: Mapping[M10TargetGroupEvidenceDomain, M10TargetGroupDomainEvidence]) -> dict[str, Any]:
    counted_domains = {
        domain: evidence
        for domain, evidence in domain_evidence.items()
        if domain in {
            M10TargetGroupEvidenceDomain.TASK,
            M10TargetGroupEvidenceDomain.COMMENT,
            M10TargetGroupEvidenceDomain.PRICE_CHANNEL,
            M10TargetGroupEvidenceDomain.MARKET,
        }
    }
    domain_scores = {domain.value: float(evidence.score) for domain, evidence in domain_evidence.items()}
    positive_domains = [domain.value for domain, evidence in counted_domains.items() if evidence.score >= Decimal("0.2500")]
    return {
        "domain_scores": domain_scores,
        "positive_domains": positive_domains,
        "positive_domain_count": len(positive_domains),
        "has_task": M10TargetGroupEvidenceDomain.TASK.value in positive_domains,
        "has_market": M10TargetGroupEvidenceDomain.MARKET.value in positive_domains,
        "has_task_or_market": M10TargetGroupEvidenceDomain.TASK.value in positive_domains or M10TargetGroupEvidenceDomain.MARKET.value in positive_domains,
    }


def _confidence(score: Decimal, profile_confidence: Any, coverage: Mapping[str, Any]) -> Decimal:
    domain_count = Decimal(int(coverage.get("positive_domain_count") or 0))
    domain_factor = min(domain_count / Decimal("4"), D1)
    return _clamp(score * Decimal("0.6500") + _decimal(profile_confidence) * Decimal("0.2500") + domain_factor * Decimal("0.1000"))


def _confidence_level(confidence: Decimal) -> Core3ConfidenceLevel:
    if confidence >= Decimal("0.7000"):
        return Core3ConfidenceLevel.HIGH
    if confidence >= Decimal("0.5000"):
        return Core3ConfidenceLevel.MEDIUM
    if confidence > 0:
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def _relation_reason_json(
    relation_level: M10TargetGroupRelationLevel,
    coverage: Mapping[str, Any],
    risk: _RiskEvaluation,
) -> dict[str, Any]:
    return {
        "relation_level": relation_level.value,
        "positive_domains": coverage.get("positive_domains") or [],
        "caps": list(risk.caps),
        "issues": list(risk.review_issues),
    }


def _missing_signals(domain_evidence: Mapping[M10TargetGroupEvidenceDomain, M10TargetGroupDomainEvidence]) -> list[dict[str, Any]]:
    return [
        {"domain": domain.value, "reason_cn": evidence.reason_cn}
        for domain, evidence in domain_evidence.items()
        if evidence.support_level == M10TargetGroupSupportLevel.MISSING
    ]


def _candidate_reason_cn(status: M10TargetGroupCandidateStatus, group_name: str, business_parts: Mapping[str, str]) -> str:
    if status == M10TargetGroupCandidateStatus.BLOCKED:
        return business_parts.get("待复核点", "输入阻塞。")
    if status == M10TargetGroupCandidateStatus.REJECTED:
        return f"{group_name} 的任务、评论、价格渠道和市场验证均不足，暂不作为目标客群。"
    if status == M10TargetGroupCandidateStatus.REVIEW_REQUIRED:
        return f"{group_name} 已有客群线索，但存在待复核限制：{business_parts.get('待复核点', '')}"
    return f"{group_name} 已进入目标客群候选，判断依据为购买任务、用户线索、价格渠道和市场验证。"


def _processing_status(status: M10TargetGroupCandidateStatus, issues: Sequence[Mapping[str, Any]]) -> str:
    if status == M10TargetGroupCandidateStatus.BLOCKED:
        return "blocked"
    if issues:
        return "warning"
    return "success"


def _support_level(score: Decimal) -> M10TargetGroupSupportLevel:
    if score >= Decimal("0.7500"):
        return M10TargetGroupSupportLevel.STRONG
    if score >= Decimal("0.5500"):
        return M10TargetGroupSupportLevel.MEDIUM
    if score > 0:
        return M10TargetGroupSupportLevel.WEAK
    return M10TargetGroupSupportLevel.MISSING


def _keyword_hit(group: Mapping[str, Any], phrases: Sequence[str]) -> bool:
    tokens = [str(item).lower() for item in [*list(group.get("aliases") or []), *list(group.get("keywords") or [])] if item]
    corpus = " ".join(str(item).lower() for item in phrases if item)
    return bool(corpus and any(token.lower() in corpus for token in tokens))


def _price_mismatch(group_code: str, screen_size: Decimal, price_band: str) -> bool:
    if group_code == "TG_VALUE_BUYER" and price_band in {"mid_high", "high"}:
        return True
    if group_code == "TG_BEDROOM_SECOND_TV" and screen_size >= Decimal("75"):
        return True
    return False


def _price_band_cn(price_band: str) -> str:
    return {
        "low": "低价位",
        "mid_low": "中低价位",
        "mid": "主流价位",
        "mid_high": "中高价位",
        "high": "高价位",
    }.get(price_band, price_band or "未知价位")


def _issue(issue_type: M10TargetGroupReviewIssueType, reason_cn: str, *, severity: str = "warning") -> dict[str, Any]:
    return {
        "issue_type": issue_type.value,
        "reason_cn": reason_cn,
        "severity": severity,
        "suggestion_cn": "补充上游证据或业务复核后重新运行 M10。",
    }


def _feature_view_hash(bundle: M10InputBundle) -> str:
    return bundle.feature_view.view_hash if bundle.feature_view is not None else "missing_feature_view"


def _record_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash([str(item) for item in parts], version=f'{prefix}_id_v1')[:24]}"


def _decimal(value: Any) -> Decimal:
    if value is None:
        return D0
    return Decimal(str(value))


def _clamp(value: Decimal) -> Decimal:
    return max(D0, min(D1, _round4(value)))


def _round4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _dedupe(values: Sequence[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = str(value)
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result


def _dedupe_issue_dicts(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = f"{value.get('issue_type')}:{value.get('reason_cn')}"
        if key in seen:
            continue
        result.append(dict(value))
        seen.add(key)
    return result


def _assert_no_forbidden_fields(payload: Mapping[str, Any]) -> None:
    for key, value in payload.items():
        if key in CORE3_M10_FORBIDDEN_OUTPUT_FIELDS:
            raise ValueError(f"M10 输出越界字段：{key}")
        if isinstance(value, Mapping):
            _assert_no_forbidden_fields(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    _assert_no_forbidden_fields(item)
