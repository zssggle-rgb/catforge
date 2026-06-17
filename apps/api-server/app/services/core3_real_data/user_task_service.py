"""M09 user-task inference service."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from app.services.core3_real_data.constants import (
    CORE3_M09_EVIDENCE_DOMAINS,
    CORE3_M09_FORBIDDEN_OUTPUT_FIELDS,
    CORE3_M09_RULE_VERSION,
    CORE3_M09_SEED_VERSION,
    Core3RunStatus,
    M08ProfileStatus,
    M09TaskCandidateSource,
    M09TaskCandidateStatus,
    M09TaskEvidenceDomain,
    M09TaskRelationLevel,
    M09TaskReviewIssueType,
    M09TaskSupportLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.task_seed_loader import M09TaskSeed, M09TaskSeedLoader
from app.services.core3_real_data.user_task_repositories import M09InputBundle, M09UserTaskRepository
from app.services.core3_real_data.user_task_schemas import (
    M09ServiceResult,
    M09SkuTaskCandidateRecord,
    M09SkuTaskEvidenceBreakdownRecord,
    M09SkuTaskReviewIssueRecord,
    M09SkuTaskScoreRecord,
    M09TaskBuildResult,
    M09TaskDomainEvidence,
)


D0 = Decimal("0")
D1 = Decimal("1")


@dataclass(frozen=True)
class _TaskScoreContext:
    bundle: M09InputBundle
    task: Mapping[str, Any]
    seed: M09TaskSeed
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


class UserTaskService:
    def __init__(self, repository: M09UserTaskRepository, seed_loader: M09TaskSeedLoader | None = None) -> None:
        self.repository = repository
        self.seed_loader = seed_loader or M09TaskSeedLoader()

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M09_RULE_VERSION,
    ) -> M09ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        seed = self.seed_loader.load()
        input_bundles = self.repository.list_input_bundles(batch_id, sku_scope=sku_scope)

        build_results: list[M09TaskBuildResult] = []
        for bundle in input_bundles:
            for task in seed.tasks:
                build_results.append(
                    self._build_task(
                        _TaskScoreContext(
                            bundle=bundle,
                            task=task,
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
            "task_seed_version": seed.seed_version,
            "task_seed_file_version": seed.file_version,
            "task_seed_hash": seed.seed_hash,
            "task_seed_task_count": seed.task_count,
            "sku_count": len(input_bundles),
            "task_candidate_count": len(candidates),
            "task_score_count": len(scores),
            "task_evidence_breakdown_count": len(breakdowns),
            "task_review_issue_count": len(review_issues),
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
                "M09 只基于 M08 SKU 综合信号画像和 M09 特征视图推导用户任务，"
                "不生成目标客群、价值战场、候选 SKU、核心竞品或高层报告。"
            ),
            "downstream_support": {
                "M10": "消费用户任务强弱关系推导目标客群候选",
                "M11": "消费用户任务与四域证据推导价值战场候选",
                "M12": "消费用户任务相似性辅助候选召回",
                "M13": "消费任务关系和证据拆分进行 pair 级评分",
                "M15": "消费业务原因和证据拆分解释为什么服务这些任务",
            },
        }
        return M09ServiceResult(
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

    def _build_task(self, context: _TaskScoreContext) -> M09TaskBuildResult:
        profile = context.bundle.profile
        view = context.bundle.feature_view
        task_code = str(context.task["task_code"])
        task_name = str(context.task["task_name"])
        task_definition = str(context.task["definition"])
        common = _common_output_fields(context)

        if view is None:
            return self._blocked_task(
                context,
                blocked_reason="缺少 M08 为 M09 准备的特征视图，不能推导用户任务。",
                issue_type=M09TaskReviewIssueType.MISSING_FEATURE_VIEW.value,
            )
        if profile.profile_status in {M08ProfileStatus.INSUFFICIENT.value, M08ProfileStatus.BLOCKED.value}:
            return self._blocked_task(
                context,
                blocked_reason="M08 SKU 综合画像状态不足，不能生成用户任务判断。",
                issue_type=M09TaskReviewIssueType.PROFILE_BLOCKED.value,
            )

        payload = dict(view.feature_payload_json or {})
        domain_evidence = {
            M09TaskEvidenceDomain.PARAM: _score_param_domain(context.task, payload, context.bundle),
            M09TaskEvidenceDomain.CLAIM: _score_claim_domain(context.task, payload, context.bundle),
            M09TaskEvidenceDomain.COMMENT: _score_comment_domain(context.task, payload, context.bundle),
            M09TaskEvidenceDomain.MARKET: _score_market_domain(context.task, payload, context.bundle),
        }
        risk = _evaluate_risk(context, domain_evidence)
        score_rule = dict(context.task.get("score_rule") or {})
        param_score = domain_evidence[M09TaskEvidenceDomain.PARAM].score
        claim_score = domain_evidence[M09TaskEvidenceDomain.CLAIM].score
        comment_score = domain_evidence[M09TaskEvidenceDomain.COMMENT].score
        market_score = domain_evidence[M09TaskEvidenceDomain.MARKET].score
        raw_score = _round4(
            claim_score * _rule_weight(score_rule, "claim")
            + param_score * _rule_weight(score_rule, "param")
            + comment_score * _rule_weight(score_rule, "comment")
            + market_score * _rule_weight(score_rule, "market")
        )
        task_score = _clamp(raw_score - risk.penalty)
        for cap in risk.caps:
            max_score = _decimal(cap.get("max_score"))
            if task_score > max_score:
                task_score = max_score
        coverage = _domain_coverage_json(domain_evidence)
        relation_level = _relation_level(task_score, coverage, risk)
        candidate_status = _candidate_status(relation_level, risk, domain_evidence)
        confidence = _confidence(task_score, profile.confidence, coverage)
        candidate_sources = _candidate_sources(domain_evidence, payload)
        business_parts = {
            "能力基础": domain_evidence[M09TaskEvidenceDomain.PARAM].reason_cn,
            "价值表达": domain_evidence[M09TaskEvidenceDomain.CLAIM].reason_cn,
            "用户反馈": domain_evidence[M09TaskEvidenceDomain.COMMENT].reason_cn,
            "市场验证": domain_evidence[M09TaskEvidenceDomain.MARKET].reason_cn,
            "待复核点": "；".join(item["reason_cn"] for item in risk.review_issues) or "暂无阻断性问题",
        }
        business_reason = "；".join(f"{key}：{value}" for key, value in business_parts.items())
        input_fingerprint = stable_hash(
            {
                "profile_hash": profile.profile_hash,
                "feature_view_hash": view.view_hash,
                "task_seed_hash": context.seed.seed_hash,
                "task_code": task_code,
                "rule_version": context.rule_version,
            },
            version="m09_task_input_v1",
        )
        candidate_id = _record_id("m09c", context.batch_id, profile.sku_code, task_code, context.seed.seed_hash)
        score_id = _record_id("m09s", context.batch_id, profile.sku_code, task_code, context.seed.seed_hash)
        candidate_payload = {
            **common,
            "sku_task_candidate_id": candidate_id,
            "task_code": task_code,
            "task_name_cn": task_name,
            "task_definition_cn": task_definition,
            "candidate_status": candidate_status,
            "candidate_sources_json": candidate_sources,
            "candidate_source_count": len(candidate_sources),
            "initial_candidate_score": task_score,
            "candidate_reason_cn": _candidate_reason_cn(candidate_status, task_name, business_parts),
            "candidate_reason_parts_json": business_parts,
            "candidate_evidence_refs_json": _dedupe(
                [item for evidence in domain_evidence.values() for item in evidence.evidence_refs]
            )[:100],
            "rejected_reason_json": {"reason_cn": "四域证据不足"} if candidate_status == M09TaskCandidateStatus.REJECTED else {},
            "blocked_reason_json": {"reason_cn": risk.blocked_reason} if risk.blocked_reason else {},
            "input_fingerprint": input_fingerprint,
            "result_hash": stable_hash(
                {"candidate_status": candidate_status, "task_score": task_score, "sources": candidate_sources},
                version="m09_candidate_result_v1",
            ),
            "processing_status": _processing_status(candidate_status, risk.review_issues),
            "review_required": bool(risk.review_issues),
            "review_status": "review_required" if risk.review_issues else "auto_pass",
            "review_reason_json": {"issues": list(risk.review_issues)},
        }
        score_payload = {
            **common,
            "sku_task_score_id": score_id,
            "sku_task_candidate_id": candidate_id,
            "task_code": task_code,
            "task_name_cn": task_name,
            "task_score": task_score,
            "raw_task_score": raw_score,
            "relation_level": relation_level,
            "confidence": confidence,
            "param_signal_score": param_score,
            "claim_signal_score": claim_score,
            "comment_signal_score": comment_score,
            "market_signal_score": market_score,
            "risk_penalty": risk.penalty,
            "cap_applied_json": list(risk.caps),
            "evidence_domain_coverage_json": coverage,
            "business_reason_cn": business_reason,
            "business_reason_parts_json": business_parts,
            "next_module_payload_json": {
                "task_code": task_code,
                "task_name_cn": task_name,
                "relation_level": relation_level,
                "task_score": float(task_score),
                "confidence": float(confidence),
                "evidence_domain_coverage": coverage,
                "source_module": "M09",
            },
            "input_fingerprint": input_fingerprint,
            "result_hash": stable_hash(
                {
                    "task_code": task_code,
                    "task_score": task_score,
                    "relation_level": relation_level,
                    "confidence": confidence,
                    "business_parts": business_parts,
                },
                version="m09_score_result_v1",
            ),
            "processing_status": _processing_status(candidate_status, risk.review_issues),
            "review_required": bool(risk.review_issues),
            "review_status": "review_required" if risk.review_issues else "auto_pass",
            "review_reason_json": {"issues": list(risk.review_issues)},
        }
        breakdowns = _breakdown_records(
            context=context,
            score_id=score_id,
            task_name=task_name,
            domain_evidence=domain_evidence,
            risk=risk,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        review_issues = _review_issue_records(
            context=context,
            candidate_id=candidate_id,
            score_id=score_id,
            task_name=task_name,
            issues=risk.review_issues,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        return M09TaskBuildResult(
            candidate=M09SkuTaskCandidateRecord(**candidate_payload),
            score=M09SkuTaskScoreRecord(**score_payload),
            breakdowns=breakdowns,
            review_issues=review_issues,
        )

    def _blocked_task(
        self,
        context: _TaskScoreContext,
        *,
        blocked_reason: str,
        issue_type: str,
    ) -> M09TaskBuildResult:
        task_code = str(context.task["task_code"])
        task_name = str(context.task["task_name"])
        task_definition = str(context.task["definition"])
        common = _common_output_fields(context)
        input_fingerprint = stable_hash(
            {
                "profile_hash": context.bundle.profile.profile_hash,
                "feature_view_hash": _feature_view_hash(context.bundle),
                "task_seed_hash": context.seed.seed_hash,
                "task_code": task_code,
                "blocked": blocked_reason,
            },
            version="m09_task_input_v1",
        )
        candidate_id = _record_id("m09c", context.batch_id, context.bundle.profile.sku_code, task_code, context.seed.seed_hash)
        score_id = _record_id("m09s", context.batch_id, context.bundle.profile.sku_code, task_code, context.seed.seed_hash)
        issue = {
            "issue_type": issue_type,
            "reason_cn": blocked_reason,
            "severity": "blocking",
            "suggestion_cn": "先补齐 M08 画像或特征视图，再重新运行 M09。",
        }
        candidate = M09SkuTaskCandidateRecord(
            **{
                **common,
                "sku_task_candidate_id": candidate_id,
                "task_code": task_code,
                "task_name_cn": task_name,
                "task_definition_cn": task_definition,
                "candidate_status": M09TaskCandidateStatus.BLOCKED,
                "candidate_sources_json": [],
                "candidate_source_count": 0,
                "initial_candidate_score": D0,
                "candidate_reason_cn": blocked_reason,
                "candidate_reason_parts_json": {"待复核点": blocked_reason},
                "candidate_evidence_refs_json": [],
                "blocked_reason_json": {"reason_cn": blocked_reason},
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(issue, version="m09_candidate_result_v1"),
                "processing_status": "blocked",
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {"issues": [issue]},
            }
        )
        score = M09SkuTaskScoreRecord(
            **{
                **common,
                "sku_task_score_id": score_id,
                "sku_task_candidate_id": candidate_id,
                "task_code": task_code,
                "task_name_cn": task_name,
                "task_score": D0,
                "raw_task_score": D0,
                "relation_level": M09TaskRelationLevel.BLOCKED,
                "confidence": D0,
                "business_reason_cn": blocked_reason,
                "business_reason_parts_json": {"待复核点": blocked_reason},
                "next_module_payload_json": {
                    "task_code": task_code,
                    "task_name_cn": task_name,
                    "relation_level": M09TaskRelationLevel.BLOCKED.value,
                    "task_score": 0.0,
                    "confidence": 0.0,
                    "source_module": "M09",
                },
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(issue, version="m09_score_result_v1"),
                "processing_status": "blocked",
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {"issues": [issue]},
            }
        )
        empty_domains = {
            domain: M09TaskDomainEvidence(
                domain=domain,
                support_level=M09TaskSupportLevel.MISSING,
                score=D0,
                weight=_domain_weight(context.task, domain),
                reason_cn=blocked_reason if domain == M09TaskEvidenceDomain.RISK else "上游输入不足，暂无法判断。",
            )
            for domain in (M09TaskEvidenceDomain.PARAM, M09TaskEvidenceDomain.CLAIM, M09TaskEvidenceDomain.COMMENT, M09TaskEvidenceDomain.MARKET)
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
            task_name=task_name,
            domain_evidence=empty_domains,
            risk=risk,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        review_issues = _review_issue_records(
            context=context,
            candidate_id=candidate_id,
            score_id=score_id,
            task_name=task_name,
            issues=(issue,),
            common=common,
            input_fingerprint=input_fingerprint,
        )
        return M09TaskBuildResult(candidate=candidate, score=score, breakdowns=breakdowns, review_issues=review_issues)


def _score_param_domain(task: Mapping[str, Any], payload: Mapping[str, Any], bundle: M09InputBundle) -> M09TaskDomainEvidence:
    param_values = dict((payload.get("core_params") or {}).get("param_values") or {})
    wanted_codes = _task_codes(task, "positive_param_codes", "mapped_param_codes")
    matched = []
    scores: list[Decimal] = []
    evidence_refs: list[str] = []
    for code in wanted_codes:
        if code not in param_values:
            continue
        item = dict(param_values[code] or {})
        score = _param_value_score(code, item)
        matched.append({"param_code": code, "score": float(score), "value": item.get("value"), "numeric_value": item.get("numeric_value")})
        scores.append(score)
        evidence_refs.extend(str(eid) for eid in item.get("evidence_ids") or [])
    if not scores:
        return M09TaskDomainEvidence(
            domain=M09TaskEvidenceDomain.PARAM,
            support_level=M09TaskSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(task, M09TaskEvidenceDomain.PARAM),
            reason_cn="关键参数未形成可用能力证据。",
            evidence_refs=[],
            source_feature_refs=[{"feature": "core_params.param_values", "expected": wanted_codes}],
        )
    score = _round4(sum(scores) / Decimal(len(scores)))
    support_level = _support_level(score)
    reason = f"命中 {len(matched)} 项任务相关参数，代表能力包括 {', '.join(item['param_code'] for item in matched[:4])}。"
    return M09TaskDomainEvidence(
        domain=M09TaskEvidenceDomain.PARAM,
        support_level=support_level,
        score=score,
        weight=_domain_weight(task, M09TaskEvidenceDomain.PARAM),
        reason_cn=reason,
        evidence_refs=_dedupe(evidence_refs),
        source_feature_refs=matched,
        risk_json={"conflict_count": _param_conflict_count(bundle)},
    )


def _score_claim_domain(task: Mapping[str, Any], payload: Mapping[str, Any], bundle: M09InputBundle) -> M09TaskDomainEvidence:
    claim_summary = dict(payload.get("claim_activation_summary") or {})
    top_claims = list(claim_summary.get("top_claims") or [])
    wanted_codes = set(_task_codes(task, "positive_claim_codes", "mapped_claim_codes"))
    matched = []
    scores: list[Decimal] = []
    for claim in top_claims:
        claim_code = str(claim.get("claim_code_hint") or "")
        if claim_code not in wanted_codes:
            continue
        score = max(_activation_level_score(str(claim.get("activation_level") or "")), _decimal(claim.get("final_activation_score")))
        score = _clamp(score)
        matched.append(
            {
                "claim_code": claim_code,
                "claim_name": claim.get("claim_name"),
                "activation_level": claim.get("activation_level"),
                "score": float(score),
            }
        )
        scores.append(score)
    if not scores:
        return M09TaskDomainEvidence(
            domain=M09TaskEvidenceDomain.CLAIM,
            support_level=M09TaskSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(task, M09TaskEvidenceDomain.CLAIM),
            reason_cn="结构化卖点尚未直接表达该任务价值。",
            source_feature_refs=[{"feature": "claim_activation_summary.top_claims", "expected": sorted(wanted_codes)}],
            risk_json={
                "missing_structured_claim_count": claim_summary.get("missing_structured_claim_count", 0),
                "param_only_count": claim_summary.get("param_only_count", 0),
                "comment_only_count": claim_summary.get("comment_only_count", 0),
            },
        )
    score = _round4(sum(scores) / Decimal(len(scores)))
    reason = f"卖点表达命中 {len(matched)} 项，主要围绕 {', '.join(item['claim_code'] for item in matched[:4])}。"
    return M09TaskDomainEvidence(
        domain=M09TaskEvidenceDomain.CLAIM,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(task, M09TaskEvidenceDomain.CLAIM),
        reason_cn=reason,
        evidence_refs=_matrix_evidence_refs(bundle, "claim"),
        source_feature_refs=matched,
        risk_json={
            "missing_structured_claim_count": claim_summary.get("missing_structured_claim_count", 0),
            "param_only_count": claim_summary.get("param_only_count", 0),
            "comment_only_count": claim_summary.get("comment_only_count", 0),
        },
    )


def _score_comment_domain(task: Mapping[str, Any], payload: Mapping[str, Any], bundle: M09InputBundle) -> M09TaskDomainEvidence:
    comment_summary = dict(payload.get("comment_signal_summary") or {})
    type_summary = dict(comment_summary.get("signal_type_summary") or {})
    task_summary = dict(type_summary.get("task_cue") or {})
    target_hints = [str(item) for item in task_summary.get("target_code_hints") or []]
    top_phrases = [str(item) for item in task_summary.get("top_phrases") or []]
    task_code = str(task.get("task_code") or "")
    keyword_hit = _keyword_hit(task, top_phrases)
    if task_code not in target_hints and not keyword_hit:
        return M09TaskDomainEvidence(
            domain=M09TaskEvidenceDomain.COMMENT,
            support_level=M09TaskSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(task, M09TaskEvidenceDomain.COMMENT),
            reason_cn="评论中暂未形成该任务的稳定场景反馈。",
            source_feature_refs=[{"feature": "comment_signal_summary.task_cue", "target_code_hints": target_hints[:12]}],
        )
    strong_count = int(task_summary.get("strong_count") or 0)
    medium_count = int(task_summary.get("medium_count") or 0)
    signal_count = int(task_summary.get("signal_count") or 0)
    score = Decimal("0.9000") if strong_count else Decimal("0.7000")
    if keyword_hit and task_code not in target_hints:
        score = Decimal("0.4500")
    if signal_count <= 1:
        score = min(score, Decimal("0.5500"))
    reason = f"评论场景出现该任务线索，强信号 {strong_count} 条、中信号 {medium_count} 条。"
    return M09TaskDomainEvidence(
        domain=M09TaskEvidenceDomain.COMMENT,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(task, M09TaskEvidenceDomain.COMMENT),
        reason_cn=reason,
        evidence_refs=_matrix_evidence_refs(bundle, "comment", ("task_cue", "claim_validation")),
        source_feature_refs=[{"feature": "comment_signal_summary.task_cue", "target_code_hints": target_hints[:12], "top_phrases": top_phrases[:8]}],
        dedup_comment_count=signal_count,
        effective_sentence_count=strong_count + medium_count,
    )


def _score_market_domain(task: Mapping[str, Any], payload: Mapping[str, Any], bundle: M09InputBundle) -> M09TaskDomainEvidence:
    market_summary = dict(payload.get("market_summary") or {})
    market_signals = [str(item) for item in task.get("market_signals") or []]
    scores: list[Decimal] = []
    reasons: list[str] = []
    screen_size = _decimal(market_summary.get("screen_size_inch"))
    price_band = str(market_summary.get("price_band_category") or market_summary.get("price_band_size") or "")
    price = _decimal(market_summary.get("price_wavg"))
    volume = _decimal(market_summary.get("sales_volume_total"))
    amount = _decimal(market_summary.get("sales_amount_total"))
    if any(signal in market_signals for signal in ("family_size_demand", "large_screen_demand")) and screen_size >= Decimal("75"):
        scores.append(Decimal("0.8000") if screen_size >= Decimal("85") else Decimal("0.7000"))
        reasons.append(f"{int(screen_size)} 英寸大屏具备任务市场基础")
    if any(signal in market_signals for signal in ("premium_price_band", "mid_high_price_band", "gaming_price_band")) and price_band in {"mid_high", "high"}:
        scores.append(Decimal("0.7500"))
        reasons.append(f"价位处于 {price_band}，与该任务价格层级匹配")
    if any(signal in market_signals for signal in ("value_price_band", "price_value_sensitive")) and price_band in {"low", "mid_low", "mid"}:
        scores.append(Decimal("0.7600"))
        reasons.append(f"价位处于 {price_band}，具备性价比任务基础")
    if "high_sales_amount" in market_signals and amount > 0:
        scores.append(Decimal("0.6500") if amount >= Decimal("1000000") else Decimal("0.4500"))
        reasons.append("销售额提供市场接受度参考")
    if "high_sales_volume" in market_signals and volume > 0:
        scores.append(Decimal("0.6500") if volume >= Decimal("500") else Decimal("0.4500"))
        reasons.append("销量提供市场接受度参考")
    if not scores and (price > 0 or volume > 0 or amount > 0):
        scores.append(Decimal("0.3000"))
        reasons.append("已有市场数据，但与该任务映射较弱")
    if not scores:
        return M09TaskDomainEvidence(
            domain=M09TaskEvidenceDomain.MARKET,
            support_level=M09TaskSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(task, M09TaskEvidenceDomain.MARKET),
            reason_cn="市场价格、销量或渠道信息不足以验证该任务。",
            source_feature_refs=[{"feature": "market_summary", "expected": market_signals}],
        )
    score = _round4(sum(scores) / Decimal(len(scores)))
    return M09TaskDomainEvidence(
        domain=M09TaskEvidenceDomain.MARKET,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(task, M09TaskEvidenceDomain.MARKET),
        reason_cn="；".join(reasons),
        evidence_refs=_matrix_evidence_refs(bundle, "market"),
        source_feature_refs=[{"feature": "market_summary", "market_signals": market_signals, "price_band": price_band}],
        risk_json={"sample_status": market_summary.get("sample_status"), "quality_flags": market_summary.get("quality_flags") or []},
    )


def _evaluate_risk(
    context: _TaskScoreContext,
    domain_evidence: Mapping[M09TaskEvidenceDomain, M09TaskDomainEvidence],
) -> _RiskEvaluation:
    issues: list[dict[str, Any]] = []
    caps: list[dict[str, Any]] = []
    penalty = D0
    positive_domains = [
        domain
        for domain, evidence in domain_evidence.items()
        if evidence.score >= Decimal("0.2500")
    ]
    if positive_domains == [M09TaskEvidenceDomain.COMMENT]:
        caps.append({"rule": "comment_only", "max_score": "0.4900", "reason_cn": "评论单域只能形成弱任务线索。"})
        issues.append(_issue(M09TaskReviewIssueType.COMMENT_ONLY, "该任务主要来自评论线索，缺少参数、卖点或市场补强。"))
    if positive_domains == [M09TaskEvidenceDomain.PARAM]:
        caps.append({"rule": "single_param_only", "max_score": "0.4900", "reason_cn": "单参数不能直接形成强任务判断。"})
        issues.append(_issue(M09TaskReviewIssueType.SINGLE_PARAM_ONLY, "该任务主要来自单一参数，缺少价值表达或用户场景。"))
    claim = domain_evidence[M09TaskEvidenceDomain.CLAIM]
    if claim.score == D0 and (
        domain_evidence[M09TaskEvidenceDomain.PARAM].score > 0 or domain_evidence[M09TaskEvidenceDomain.COMMENT].score > 0
    ):
        penalty += Decimal("0.0400")
        issues.append(_issue(M09TaskReviewIssueType.CLAIM_MISSING, "缺少该任务的结构化卖点表达，需在展示中降低卖点确定性。"))
    market_risk = domain_evidence[M09TaskEvidenceDomain.MARKET].risk_json
    if market_risk.get("sample_status") in {"limited", "insufficient"}:
        penalty += Decimal("0.0300")
        issues.append(_issue(M09TaskReviewIssueType.MARKET_LIMITED, "市场样本有限，价格和销量验证只能作为辅助证据。"))
    if _param_conflict_count(context.bundle) > 0:
        penalty += Decimal("0.0300")
        issues.append(_issue(M09TaskReviewIssueType.CONFLICT, "关键参数画像存在冲突，任务能力基础需要复核。"))
    return _RiskEvaluation(penalty=_clamp(penalty), caps=tuple(caps), review_issues=tuple(_dedupe_issue_dicts(issues)))


def _breakdown_records(
    *,
    context: _TaskScoreContext,
    score_id: str,
    task_name: str,
    domain_evidence: Mapping[M09TaskEvidenceDomain, M09TaskDomainEvidence],
    risk: _RiskEvaluation,
    common: Mapping[str, Any],
    input_fingerprint: str,
) -> list[M09SkuTaskEvidenceBreakdownRecord]:
    records: list[M09SkuTaskEvidenceBreakdownRecord] = []
    breakdown_common = _without_profile_view_refs(common)
    for domain in CORE3_M09_EVIDENCE_DOMAINS:
        if domain in domain_evidence:
            evidence = domain_evidence[domain]
        elif domain == M09TaskEvidenceDomain.RISK:
            evidence = M09TaskDomainEvidence(
                domain=domain,
                support_level=M09TaskSupportLevel.CONFLICT if risk.review_issues else M09TaskSupportLevel.NOT_APPLICABLE,
                score=risk.penalty,
                weight=D0,
                reason_cn="；".join(item["reason_cn"] for item in risk.review_issues) or "未发现需要封顶或降级的风险。",
                risk_json={"caps": list(risk.caps), "issues": list(risk.review_issues)},
            )
        elif domain == M09TaskEvidenceDomain.SEED:
            evidence = M09TaskDomainEvidence(
                domain=domain,
                support_level=M09TaskSupportLevel.STRONG,
                score=D1,
                weight=D0,
                reason_cn="任务本体来自固定 TV MVP seed，当前仅作为推导框架，不直接代表 SKU 结论。",
                source_feature_refs=[{"task_seed_version": context.seed.seed_version, "task_seed_hash": context.seed.seed_hash}],
            )
        else:
            profile = context.bundle.profile
            evidence = M09TaskDomainEvidence(
                domain=domain,
                support_level=_support_level(_decimal(profile.confidence)),
                score=_clamp(_decimal(profile.confidence)),
                weight=D0,
                reason_cn=f"M08 综合画像完整度 {float(profile.data_completeness_score or 0):.2f}，作为任务判断的底层可信度参考。",
                evidence_refs=list(profile.representative_evidence_ids or [])[:20],
                source_feature_refs=[{"profile_hash": profile.profile_hash, "profile_status": profile.profile_status}],
            )
        weighted = _round4(evidence.score * evidence.weight)
        payload = {
            "sku_code": context.bundle.profile.sku_code,
            "task_code": context.task["task_code"],
            "domain": domain.value,
            "score": evidence.score,
            "weight": evidence.weight,
            "input_fingerprint": input_fingerprint,
        }
        records.append(
            M09SkuTaskEvidenceBreakdownRecord(
                **{
                    **breakdown_common,
                    "sku_task_evidence_breakdown_id": _record_id(
                        "m09b",
                        context.batch_id,
                        context.bundle.profile.sku_code,
                        context.task["task_code"],
                        domain.value,
                        context.seed.seed_hash,
                    ),
                    "sku_task_score_id": score_id,
                    "task_code": str(context.task["task_code"]),
                    "task_name_cn": task_name,
                    "evidence_domain": domain,
                    "support_level": evidence.support_level,
                    "domain_score": evidence.score,
                    "domain_weight": evidence.weight,
                    "weighted_score": weighted,
                    "evidence_count": len(evidence.evidence_refs),
                    "dedup_comment_count": evidence.dedup_comment_count,
                    "effective_sentence_count": evidence.effective_sentence_count,
                    "evidence_refs_json": evidence.evidence_refs[:100],
                    "source_feature_refs_json": evidence.source_feature_refs,
                    "domain_reason_cn": evidence.reason_cn,
                    "domain_risk_json": evidence.risk_json,
                    "input_fingerprint": input_fingerprint,
                    "result_hash": stable_hash(payload, version="m09_breakdown_result_v1"),
                    "review_required": domain == M09TaskEvidenceDomain.RISK and bool(risk.review_issues),
                    "review_status": "review_required" if domain == M09TaskEvidenceDomain.RISK and risk.review_issues else "auto_pass",
                    "review_reason_json": {"issues": list(risk.review_issues)} if domain == M09TaskEvidenceDomain.RISK else {},
                }
            )
        )
    return records


def _review_issue_records(
    *,
    context: _TaskScoreContext,
    candidate_id: str,
    score_id: str,
    task_name: str,
    issues: Sequence[Mapping[str, Any]],
    common: Mapping[str, Any],
    input_fingerprint: str,
) -> list[M09SkuTaskReviewIssueRecord]:
    records: list[M09SkuTaskReviewIssueRecord] = []
    issue_common = _without_profile_view_refs(common)
    for issue in issues:
        issue_type = str(issue.get("issue_type") or M09TaskReviewIssueType.UNKNOWN_INPUT.value)
        payload = {
            "sku_code": context.bundle.profile.sku_code,
            "task_code": context.task["task_code"],
            "issue_type": issue_type,
            "input_fingerprint": input_fingerprint,
        }
        records.append(
            M09SkuTaskReviewIssueRecord(
                **{
                    **issue_common,
                    "sku_task_review_issue_id": _record_id(
                        "m09r",
                        context.batch_id,
                        context.bundle.profile.sku_code,
                        context.task["task_code"],
                        issue_type,
                        context.seed.seed_hash,
                    ),
                    "sku_task_score_id": score_id,
                    "sku_task_candidate_id": candidate_id,
                    "task_code": str(context.task["task_code"]),
                    "task_name_cn": task_name,
                    "issue_type": issue_type,
                    "issue_severity": str(issue.get("severity") or "warning"),
                    "issue_status": "open",
                    "issue_reason_cn": str(issue.get("reason_cn") or "任务证据需要复核。"),
                    "issue_detail_json": dict(issue),
                    "affected_output_json": {"score_id": score_id, "candidate_id": candidate_id},
                    "evidence_refs_json": [],
                    "suggested_action_cn": str(issue.get("suggestion_cn") or "补充上游数据或人工复核后重新运行 M09。"),
                    "input_fingerprint": input_fingerprint,
                    "result_hash": stable_hash(payload, version="m09_review_issue_result_v1"),
                    "processing_status": "blocked" if issue.get("severity") == "blocking" else "warning",
                    "review_required": True,
                    "review_status": "review_required",
                    "review_reason_json": dict(issue),
                }
            )
        )
    return records


def _common_output_fields(context: _TaskScoreContext) -> dict[str, Any]:
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
        "task_seed_version": CORE3_M09_SEED_VERSION,
        "task_seed_file_version": context.seed.file_version,
        "task_seed_hash": context.seed.seed_hash,
        "profile_hash": profile.profile_hash,
        "feature_view_hash": _feature_view_hash(context.bundle),
    }


def _without_profile_view_refs(common: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in common.items()
        if key not in {"sku_signal_profile_id", "sku_downstream_feature_view_id"}
    }


def _relation_level(task_score: Decimal, coverage: Mapping[str, Any], risk: _RiskEvaluation) -> M09TaskRelationLevel:
    if risk.blocked_reason:
        return M09TaskRelationLevel.BLOCKED
    positive_domains = set(coverage.get("positive_domains") or [])
    if (
        task_score >= Decimal("0.7500")
        and len(positive_domains) >= 3
        and (M09TaskEvidenceDomain.PARAM.value in positive_domains or M09TaskEvidenceDomain.CLAIM.value in positive_domains)
    ):
        return M09TaskRelationLevel.MAIN
    if task_score >= Decimal("0.6000") and len(positive_domains) >= 2 and positive_domains != {M09TaskEvidenceDomain.COMMENT.value}:
        return M09TaskRelationLevel.SECONDARY
    if task_score >= Decimal("0.4000"):
        return M09TaskRelationLevel.WEAK
    return M09TaskRelationLevel.INSUFFICIENT


def _candidate_status(
    relation_level: M09TaskRelationLevel,
    risk: _RiskEvaluation,
    domain_evidence: Mapping[M09TaskEvidenceDomain, M09TaskDomainEvidence],
) -> M09TaskCandidateStatus:
    if relation_level == M09TaskRelationLevel.BLOCKED:
        return M09TaskCandidateStatus.BLOCKED
    if relation_level == M09TaskRelationLevel.INSUFFICIENT and not any(item.score > 0 for item in domain_evidence.values()):
        return M09TaskCandidateStatus.REJECTED
    if risk.review_issues:
        return M09TaskCandidateStatus.REVIEW_REQUIRED
    return M09TaskCandidateStatus.ACTIVE


def _candidate_sources(domain_evidence: Mapping[M09TaskEvidenceDomain, M09TaskDomainEvidence], payload: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    if domain_evidence[M09TaskEvidenceDomain.PARAM].score > 0:
        result.append(M09TaskCandidateSource.PARAM.value)
    if domain_evidence[M09TaskEvidenceDomain.CLAIM].score > 0:
        result.append(M09TaskCandidateSource.CLAIM.value)
    if domain_evidence[M09TaskEvidenceDomain.COMMENT].score > 0:
        result.append(M09TaskCandidateSource.COMMENT.value)
    if domain_evidence[M09TaskEvidenceDomain.MARKET].score > 0:
        result.append(M09TaskCandidateSource.MARKET.value)
    comment_types = dict((payload.get("comment_signal_summary") or {}).get("signal_type_summary") or {})
    if (comment_types.get("price_perception") or {}).get("signal_count"):
        result.append(M09TaskCandidateSource.PRICE_PERCEPTION.value)
    if (comment_types.get("service_signal") or {}).get("signal_count"):
        result.append(M09TaskCandidateSource.SERVICE_SIGNAL.value)
    return _dedupe(result)


def _domain_coverage_json(domain_evidence: Mapping[M09TaskEvidenceDomain, M09TaskDomainEvidence]) -> dict[str, Any]:
    domain_scores = {domain.value: float(evidence.score) for domain, evidence in domain_evidence.items()}
    positive_domains = [domain.value for domain, evidence in domain_evidence.items() if evidence.score >= Decimal("0.2500")]
    return {
        "domain_scores": domain_scores,
        "positive_domains": positive_domains,
        "positive_domain_count": len(positive_domains),
        "has_param_or_claim": M09TaskEvidenceDomain.PARAM.value in positive_domains or M09TaskEvidenceDomain.CLAIM.value in positive_domains,
    }


def _confidence(task_score: Decimal, profile_confidence: Any, coverage: Mapping[str, Any]) -> Decimal:
    domain_count = Decimal(int(coverage.get("positive_domain_count") or 0))
    domain_factor = min(domain_count / Decimal("4"), D1)
    value = task_score * Decimal("0.55") + _decimal(profile_confidence) * Decimal("0.30") + domain_factor * Decimal("0.15")
    return _clamp(value)


def _processing_status(candidate_status: M09TaskCandidateStatus, issues: Sequence[Mapping[str, Any]]) -> str:
    if candidate_status == M09TaskCandidateStatus.BLOCKED:
        return "blocked"
    if any(issue.get("severity") == "blocking" for issue in issues):
        return "blocked"
    if candidate_status == M09TaskCandidateStatus.REVIEW_REQUIRED or issues:
        return "review_required"
    return "success"


def _candidate_reason_cn(candidate_status: M09TaskCandidateStatus, task_name: str, parts: Mapping[str, str]) -> str:
    if candidate_status == M09TaskCandidateStatus.REJECTED:
        return f"{task_name}证据不足，暂不作为有效用户任务。"
    if candidate_status == M09TaskCandidateStatus.BLOCKED:
        return str(parts.get("待复核点") or f"{task_name}缺少必要输入。")
    return f"{task_name}由能力基础、价值表达、用户反馈和市场验证共同推导，需结合证据强弱使用。"


def _task_codes(task: Mapping[str, Any], *field_names: str) -> list[str]:
    values: list[str] = []
    for field_name in field_names:
        values.extend(str(item) for item in task.get(field_name) or [] if item)
    return _dedupe(values)


def _domain_weight(task: Mapping[str, Any], domain: M09TaskEvidenceDomain) -> Decimal:
    score_rule = dict(task.get("score_rule") or {})
    key_map = {
        M09TaskEvidenceDomain.PARAM: "param",
        M09TaskEvidenceDomain.CLAIM: "claim",
        M09TaskEvidenceDomain.COMMENT: "comment",
        M09TaskEvidenceDomain.MARKET: "market",
    }
    key = key_map.get(domain)
    return _rule_weight(score_rule, key) if key else D0


def _rule_weight(score_rule: Mapping[str, Any], domain: str) -> Decimal:
    return _decimal(score_rule.get(domain, score_rule.get(f"{domain}_weight")))


def _param_value_score(param_code: str, item: Mapping[str, Any]) -> Decimal:
    value_presence = str(item.get("value_presence") or "")
    if value_presence in {"null", "empty", "dash", "unknown_literal", "missing_column"}:
        return D0
    numeric = _decimal(item.get("numeric_value"))
    value = item.get("value")
    if param_code == "screen_size_inch":
        if numeric >= Decimal("85"):
            return Decimal("1.0000")
        if numeric >= Decimal("75"):
            return Decimal("0.8500")
        if numeric >= Decimal("65"):
            return Decimal("0.4500")
    if param_code in {"peak_brightness_nits", "dimming_zones"}:
        if numeric >= Decimal("1000") or (param_code == "dimming_zones" and numeric >= Decimal("100")):
            return Decimal("1.0000")
        if numeric >= Decimal("500"):
            return Decimal("0.7500")
    if param_code in {"native_refresh_rate_hz", "system_refresh_rate_hz"}:
        if numeric >= Decimal("120"):
            return Decimal("1.0000")
        if numeric >= Decimal("100"):
            return Decimal("0.7500")
        if numeric >= Decimal("60"):
            return Decimal("0.3500")
    if param_code == "input_lag_ms" and numeric > 0:
        return Decimal("0.9000") if numeric <= Decimal("20") else Decimal("0.4500")
    if param_code.endswith("_flag"):
        return Decimal("0.8500") if str(value).lower() in {"true", "1", "yes", "是", "支持"} else D0
    if numeric > 0:
        return Decimal("0.6500")
    if isinstance(value, dict | list):
        return Decimal("0.5500") if value else D0
    if value not in {None, "", "-", "unknown", "未知"}:
        return Decimal("0.5500")
    return D0


def _activation_level_score(level: str) -> Decimal:
    return {
        "high": Decimal("1.0000"),
        "medium": Decimal("0.7500"),
        "low": Decimal("0.4000"),
        "weak": Decimal("0.3000"),
    }.get(level, D0)


def _support_level(score: Decimal) -> M09TaskSupportLevel:
    if score >= Decimal("0.7500"):
        return M09TaskSupportLevel.STRONG
    if score >= Decimal("0.5500"):
        return M09TaskSupportLevel.MEDIUM
    if score > D0:
        return M09TaskSupportLevel.WEAK
    return M09TaskSupportLevel.MISSING


def _keyword_hit(task: Mapping[str, Any], phrases: Sequence[str]) -> bool:
    words = [str(item).lower() for key in ("aliases", "keywords") for item in task.get(key) or [] if item]
    normalized_phrases = " ".join(phrases).lower()
    return any(word and word in normalized_phrases for word in words)


def _matrix_evidence_refs(bundle: M09InputBundle, domain: str, sub_domains: Sequence[str] = ()) -> list[str]:
    refs: list[str] = []
    sub_domain_set = set(sub_domains)
    for matrix in bundle.evidence_matrices:
        if matrix.domain != domain:
            continue
        if sub_domain_set and matrix.sub_domain not in sub_domain_set:
            continue
        refs.extend(str(item) for item in matrix.representative_evidence_ids or [])
    return _dedupe(refs)[:100]


def _param_conflict_count(bundle: M09InputBundle) -> int:
    param_profile = dict(bundle.profile.param_profile_json or {})
    return int(param_profile.get("conflict_count") or 0)


def _feature_view_hash(bundle: M09InputBundle) -> str:
    return bundle.feature_view.view_hash if bundle.feature_view else "missing_feature_view"


def _issue(issue_type: M09TaskReviewIssueType, reason_cn: str, *, severity: str = "warning") -> dict[str, Any]:
    return {
        "issue_type": issue_type.value,
        "reason_cn": reason_cn,
        "severity": severity,
        "suggestion_cn": "结合上游证据补充或人工复核后再使用该任务结论。",
    }


def _dedupe_issue_dicts(issues: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for issue in issues:
        issue_type = str(issue.get("issue_type") or "")
        if issue_type in seen:
            continue
        seen.add(issue_type)
        result.append(dict(issue))
    return result


def _record_id(prefix: str, *parts: Any) -> str:
    return stable_hash([prefix, *parts], version=f"{prefix}_id_v1").split(":")[-1][:48]


def _round4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal | float | int | None) -> Decimal:
    normalized = _decimal(value)
    if normalized < D0:
        return D0
    if normalized > D1:
        return D1
    return _round4(normalized)


def _decimal(value: Any) -> Decimal:
    if value is None:
        return D0
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return D0


def _dedupe(values: Sequence[Any]) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _assert_no_forbidden_fields(payload: Any) -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key) in CORE3_M09_FORBIDDEN_OUTPUT_FIELDS:
                raise ValueError(f"M09 output must not include forbidden field: {key}")
            _assert_no_forbidden_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_forbidden_fields(item)
