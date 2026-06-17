"""M11 battlefield inference service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from app.services.core3_real_data.battlefield_repositories import M11BattlefieldRepository, M11InputBundle
from app.services.core3_real_data.battlefield_schemas import (
    M11BattlefieldBuildResult,
    M11BattlefieldDomainEvidence,
    M11ServiceResult,
    M11SkuBattlefieldCandidateRecord,
    M11SkuBattlefieldEvidenceBreakdownRecord,
    M11SkuBattlefieldPortfolioRecord,
    M11SkuBattlefieldReviewIssueRecord,
    M11SkuBattlefieldScoreRecord,
)
from app.services.core3_real_data.battlefield_seed_loader import M11BattlefieldSeed, M11BattlefieldSeedLoader
from app.services.core3_real_data.constants import (
    CORE3_M11_EVIDENCE_DOMAINS,
    CORE3_M11_FORBIDDEN_OUTPUT_FIELDS,
    CORE3_M11_RULE_VERSION,
    CORE3_M11_SEED_VERSION,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M08ProfileStatus,
    M11BattlefieldCandidateSource,
    M11BattlefieldCandidateStatus,
    M11BattlefieldEvidenceDomain,
    M11BattlefieldRelationLevel,
    M11BattlefieldReviewIssueType,
    M11BattlefieldSampleSufficiency,
    M11BattlefieldSupportLevel,
    M11CompetitorSelectionRole,
)
from app.services.core3_real_data.dimension_ontology_service import BATTLEFIELD_V2_RULES, SERVICE_BATTLEFIELD_CODE
from app.services.core3_real_data.hash_utils import stable_hash


D0 = Decimal("0")
D1 = Decimal("1")
V2_NON_PRODUCT_ACTIONS = {"merge_to", "anchor_to", "context_only"}


@dataclass(frozen=True)
class _BattlefieldScoreContext:
    bundle: M11InputBundle
    battlefield: Mapping[str, Any]
    seed: M11BattlefieldSeed
    battlefield_definition_hash: str
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


def _effective_battlefields(seed: M11BattlefieldSeed, active_definitions: Sequence[Any]) -> tuple[Mapping[str, Any], ...]:
    definitions_by_code = {str(row.dimension_code): row for row in active_definitions}
    effective: list[Mapping[str, Any]] = []
    for battlefield in seed.battlefields:
        battlefield_code = str(battlefield.get("battlefield_code") or "")
        definition = definitions_by_code.get(battlefield_code)
        if definition is None:
            effective.append(dict(battlefield))
            continue
        merged = dict(battlefield)
        merged["battlefield_name"] = definition.dimension_name_cn or merged.get("battlefield_name")
        merged["definition"] = definition.definition_cn or merged.get("definition")
        merged["_m08_5_definition"] = _definition_meta_from_row(definition)
        effective.append(merged)
    return tuple(effective)


def _definition_meta_from_row(row: Any) -> dict[str, Any]:
    include_rule = dict(row.include_rule_json or {})
    required_evidence = dict(row.required_evidence_json or {})
    downstream_policy = dict(row.downstream_policy_json or {})
    v2_definition = (
        downstream_policy.get("v2_definition")
        or required_evidence.get("v2_definition")
        or include_rule.get("v2_definition")
        or {}
    )
    return {
        "dimension_definition_id": row.dimension_definition_id,
        "ontology_version_id": row.ontology_version_id,
        "dimension_code": row.dimension_code,
        "dimension_name_cn": row.dimension_name_cn,
        "definition_cn": row.definition_cn,
        "definition_status": row.definition_status,
        "boundary_policy": row.boundary_policy,
        "allocation_policy": row.allocation_policy,
        "include_rule_json": include_rule,
        "required_evidence_json": required_evidence,
        "downstream_policy_json": downstream_policy,
        "profile_eligibility_policy_json": dict(row.profile_eligibility_policy_json or {}),
        "v2_definition": dict(v2_definition or {}),
        "support_score": str(row.support_score),
        "distinctiveness_score": str(row.distinctiveness_score),
        "sku_coverage_count": int(row.sku_coverage_count or 0),
        "strong_sku_coverage_count": int(row.strong_sku_coverage_count or 0),
        "seed_hash": row.seed_hash,
        "result_hash": row.result_hash,
    }


def _active_battlefield_definition_hash(active_definitions: Sequence[Any]) -> str:
    if not active_definitions:
        return "seed_only"
    return stable_hash(
        [
            {
                "dimension_code": row.dimension_code,
                "dimension_name_cn": row.dimension_name_cn,
                "definition_status": row.definition_status,
                "boundary_policy": row.boundary_policy,
                "allocation_policy": row.allocation_policy,
                "result_hash": row.result_hash,
            }
            for row in active_definitions
        ],
        version="m11_active_m08_5_battlefield_definition_hash_v1",
    )


class BattlefieldService:
    def __init__(self, repository: M11BattlefieldRepository, seed_loader: M11BattlefieldSeedLoader | None = None) -> None:
        self.repository = repository
        self.seed_loader = seed_loader or M11BattlefieldSeedLoader()

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M11_RULE_VERSION,
    ) -> M11ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        seed = self.seed_loader.load()
        active_battlefield_definitions = self.repository.list_current_battlefield_definitions(batch_id)
        battlefield_definition_hash = _active_battlefield_definition_hash(active_battlefield_definitions)
        battlefields = _effective_battlefields(seed, active_battlefield_definitions)
        input_bundles = self.repository.list_input_bundles(batch_id, sku_scope=sku_scope)

        build_results: list[M11BattlefieldBuildResult] = []
        for bundle in input_bundles:
            for battlefield in battlefields:
                build_results.append(
                    self._build_battlefield(
                        _BattlefieldScoreContext(
                            bundle=bundle,
                            battlefield=battlefield,
                            seed=seed,
                            battlefield_definition_hash=battlefield_definition_hash,
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
        portfolios = self._build_portfolios(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            seed=seed,
            battlefield_definition_hash=battlefield_definition_hash,
            battlefields=battlefields,
            input_bundles=input_bundles,
            scores=scores,
        )

        for payload in [score.model_dump(mode="python") for score in scores]:
            _assert_no_forbidden_fields(payload)
        for payload in [candidate.model_dump(mode="python") for candidate in candidates]:
            _assert_no_forbidden_fields(payload)
        for payload in [portfolio.model_dump(mode="python") for portfolio in portfolios]:
            _assert_no_forbidden_fields(payload)

        candidate_write = self.repository.save_candidates(candidates)
        score_write = self.repository.save_scores(scores)
        breakdown_write = self.repository.save_breakdowns(breakdowns)
        portfolio_write = self.repository.save_portfolios(portfolios)
        review_write = self.repository.save_review_issues(review_issues)

        relation_counts = Counter(score.relation_level for score in scores)
        role_counts = Counter(score.competitor_selection_role for score in scores)
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
            + portfolio_write.created_count
            + review_write.created_count
        )
        summary = {
            "batch_id": batch_id,
            "rule_version": rule_version,
            "battlefield_seed_version": seed.seed_version,
            "battlefield_seed_file_version": seed.file_version,
            "battlefield_seed_hash": seed.seed_hash,
            "battlefield_seed_count": seed.battlefield_count,
            "battlefield_definition_source": "m08_5_active_ontology" if active_battlefield_definitions else "seed_fallback",
            "active_m08_5_battlefield_definition_count": len(active_battlefield_definitions),
            "active_m08_5_battlefield_definition_hash": battlefield_definition_hash,
            "sku_count": len(input_bundles),
            "battlefield_candidate_count": len(candidates),
            "battlefield_score_count": len(scores),
            "battlefield_evidence_breakdown_count": len(breakdowns),
            "battlefield_portfolio_count": len(portfolios),
            "battlefield_review_issue_count": len(review_issues),
            "relation_level_counts": {str(key): value for key, value in relation_counts.items()},
            "competitor_selection_role_counts": {str(key): value for key, value in role_counts.items()},
            "candidate_status_counts": {str(key): value for key, value in candidate_counts.items()},
            "evidence_domain_counts": {str(key): value for key, value in domain_counts.items()},
            "created_output_count": created_count,
            "updated_output_count": (
                candidate_write.updated_count
                + score_write.updated_count
                + breakdown_write.updated_count
                + portfolio_write.updated_count
                + review_write.updated_count
            ),
            "reused_output_count": (
                candidate_write.reused_count
                + score_write.reused_count
                + breakdown_write.reused_count
                + portfolio_write.reused_count
                + review_write.reused_count
            ),
            "boundary_note": (
                "M11 只消费 M08 SKU 综合画像、M09 用户任务和 M10 目标客群结果推导价值战场，"
                "不生成卖点价值分层、候选 SKU、核心竞品或高层报告。"
            ),
            "downstream_support": {
                "M11.5": "消费战场分数和分域证据做战场内卖点价值分层",
                "M12": "消费主战场/次战场/机会战场作为候选池召回语境",
                "M13": "消费目标 SKU 与候选 SKU 的战场重合度进行 pair 级评分",
                "M14": "消费主战场和服务风险语境选择三槽位核心竞品",
                "M15": "消费战场组合与证据拆分解释为什么是竞品",
            },
        }
        return M11ServiceResult(
            candidates=candidates,
            scores=scores,
            breakdowns=breakdowns,
            portfolios=portfolios,
            review_issues=review_issues,
            summary=summary,
            warnings=warnings,
            status=status,
            input_count=len(input_bundles),
            output_count=len(candidates) + len(scores) + len(breakdowns) + len(portfolios) + len(review_issues),
            created_output_count=created_count,
        )

    def _build_battlefield(self, context: _BattlefieldScoreContext) -> M11BattlefieldBuildResult:
        profile = context.bundle.profile
        view = context.bundle.feature_view
        battlefield_code = str(context.battlefield["battlefield_code"])
        battlefield_name = str(context.battlefield["battlefield_name"])
        battlefield_definition = str(context.battlefield["definition"])
        common = _common_output_fields(context)

        if view is None:
            return self._blocked_battlefield(
                context,
                blocked_reason="缺少 M08 为 M11 准备的价值战场特征视图，不能推导价值战场。",
                issue_type=M11BattlefieldReviewIssueType.MISSING_FEATURE_VIEW.value,
            )
        if profile.profile_status in {M08ProfileStatus.INSUFFICIENT.value, M08ProfileStatus.BLOCKED.value}:
            return self._blocked_battlefield(
                context,
                blocked_reason="M08 SKU 综合画像状态不足，不能生成价值战场判断。",
                issue_type=M11BattlefieldReviewIssueType.PROFILE_BLOCKED.value,
            )
        if not context.bundle.task_scores:
            return self._blocked_battlefield(
                context,
                blocked_reason="缺少 M09 用户任务分数，不能跳过任务层直接生成价值战场。",
                issue_type=M11BattlefieldReviewIssueType.MISSING_TASK_SCORE.value,
            )
        if not context.bundle.target_group_scores:
            return self._blocked_battlefield(
                context,
                blocked_reason="缺少 M10 目标客群分数，不能跳过客群层直接生成价值战场。",
                issue_type=M11BattlefieldReviewIssueType.MISSING_TARGET_GROUP_SCORE.value,
            )

        payload = dict(view.feature_payload_json or {})
        domain_evidence = {
            M11BattlefieldEvidenceDomain.TASK: _score_task_domain(context.battlefield, context.bundle),
            M11BattlefieldEvidenceDomain.TARGET_GROUP: _score_target_group_domain(context.battlefield, context.bundle, context.seed),
            M11BattlefieldEvidenceDomain.CLAIM: _score_claim_domain(context.battlefield, payload, context.bundle),
            M11BattlefieldEvidenceDomain.PARAM: _score_param_domain(context.battlefield, payload, context.bundle),
            M11BattlefieldEvidenceDomain.COMMENT: _score_comment_domain(context.battlefield, payload, context.bundle),
            M11BattlefieldEvidenceDomain.MARKET: _score_market_domain(context.battlefield, payload, context.bundle),
            M11BattlefieldEvidenceDomain.SERVICE: _score_service_domain(context.battlefield, payload, context.bundle),
        }
        risk = _evaluate_risk(context, domain_evidence)
        task_score = domain_evidence[M11BattlefieldEvidenceDomain.TASK].score
        target_group_score = domain_evidence[M11BattlefieldEvidenceDomain.TARGET_GROUP].score
        claim_score = domain_evidence[M11BattlefieldEvidenceDomain.CLAIM].score
        param_score = domain_evidence[M11BattlefieldEvidenceDomain.PARAM].score
        comment_score = domain_evidence[M11BattlefieldEvidenceDomain.COMMENT].score
        market_domain_score = domain_evidence[M11BattlefieldEvidenceDomain.MARKET].score
        service_score = domain_evidence[M11BattlefieldEvidenceDomain.SERVICE].score
        market_parts = dict(domain_evidence[M11BattlefieldEvidenceDomain.MARKET].risk_json or {})
        price_fit = _decimal(market_parts.get("price_position_fit"))
        sales_validation = _decimal(market_parts.get("sales_validation_score"))
        sales_amount_validation = _decimal(market_parts.get("sales_amount_validation_score"))
        channel_fit = _decimal(market_parts.get("channel_fit_score"))
        trend_signal = _decimal(market_parts.get("trend_signal_score"))
        pool_strength = _decimal(market_parts.get("comparable_pool_strength"))
        market_pool_fit = _decimal(market_parts.get("market_pool_fit_score"))
        product_anchor_fit = _decimal(market_parts.get("product_anchor_fit_score"))

        semantic_score = _round4(
            task_score * Decimal("0.3000")
            + target_group_score * Decimal("0.1500")
            + claim_score * Decimal("0.2500")
            + param_score * Decimal("0.2000")
            + comment_score * Decimal("0.1000")
        )
        market_score = _round4(
            price_fit * Decimal("0.2500")
            + sales_validation * Decimal("0.2500")
            + sales_amount_validation * Decimal("0.1500")
            + channel_fit * Decimal("0.1000")
            + trend_signal * Decimal("0.1000")
            + pool_strength * Decimal("0.1500")
        )
        product_anchor_score = max(product_anchor_fit, _average([claim_score, param_score]))
        value_theme_score = _average([claim_score, param_score, comment_score])
        task_group_fit_score = _average([task_score, target_group_score])
        market_performance_score = _average([sales_validation, sales_amount_validation, channel_fit, trend_signal])
        market_pool_fit = market_pool_fit or market_score
        raw_score = _clamp(
            market_pool_fit * Decimal("0.2500")
            + product_anchor_score * Decimal("0.3000")
            + value_theme_score * Decimal("0.1500")
            + task_group_fit_score * Decimal("0.1000")
            + comment_score * Decimal("0.1000")
            + market_performance_score * Decimal("0.1000")
        )
        battlefield_score = _clamp(raw_score - risk.penalty)
        for cap in risk.caps:
            max_score = _decimal(cap.get("max_score"))
            if battlefield_score > max_score:
                battlefield_score = max_score

        coverage = _domain_coverage_json(domain_evidence)
        relation_level = _relation_level(battlefield_score, semantic_score, market_score, coverage, risk)
        selection_role = _selection_role(battlefield_code, relation_level)
        candidate_status = _candidate_status(relation_level, risk, domain_evidence)
        confidence = _confidence(battlefield_score, profile.confidence, coverage, risk)
        confidence_level = _confidence_level(confidence)
        candidate_sources = _candidate_sources(domain_evidence)
        business_parts = {
            "用户任务": domain_evidence[M11BattlefieldEvidenceDomain.TASK].reason_cn,
            "目标客群": domain_evidence[M11BattlefieldEvidenceDomain.TARGET_GROUP].reason_cn,
            "核心卖点": domain_evidence[M11BattlefieldEvidenceDomain.CLAIM].reason_cn,
            "关键参数": domain_evidence[M11BattlefieldEvidenceDomain.PARAM].reason_cn,
            "用户评论": domain_evidence[M11BattlefieldEvidenceDomain.COMMENT].reason_cn,
            "市场验证": domain_evidence[M11BattlefieldEvidenceDomain.MARKET].reason_cn,
            "服务侧面": domain_evidence[M11BattlefieldEvidenceDomain.SERVICE].reason_cn,
            "待复核点": "；".join(item["reason_cn"] for item in risk.review_issues) or "暂无阻断性问题",
        }
        business_reason = "；".join(f"{key}：{value}" for key, value in business_parts.items())
        input_fingerprint = stable_hash(
            {
                "profile_hash": profile.profile_hash,
                "feature_view_hash": view.view_hash,
                "task_score_fingerprint": context.bundle.task_score_fingerprint,
                "target_group_score_fingerprint": context.bundle.target_group_score_fingerprint,
                "battlefield_seed_hash": context.seed.seed_hash,
                "battlefield_definition_hash": context.battlefield_definition_hash,
                "battlefield_code": battlefield_code,
                "rule_version": context.rule_version,
            },
            version="m11_battlefield_input_v1",
        )
        candidate_id = _record_id("m11c", context.batch_id, profile.sku_code, battlefield_code, context.seed.seed_hash)
        score_id = _record_id("m11s", context.batch_id, profile.sku_code, battlefield_code, context.seed.seed_hash)
        evidence_ids = _dedupe([item for evidence in domain_evidence.values() for item in evidence.evidence_ids])[:120]
        matrix_refs = _dedupe([item.sku_signal_evidence_matrix_id for item in context.bundle.evidence_matrices])[:120]
        missing_signals = _missing_signals(domain_evidence)
        risk_flags = list(risk.review_issues)
        source_tasks = _source_task_codes(context.battlefield)
        source_groups = list(context.seed.target_groups_by_battlefield.get(battlefield_code, ()))
        source_claims = _source_claim_codes(context.battlefield)
        source_params = _source_param_codes(context.battlefield)
        source_topics = _source_topic_codes(context.battlefield)
        candidate_payload = {
            **common,
            "sku_battlefield_candidate_id": candidate_id,
            "battlefield_code": battlefield_code,
            "battlefield_name_cn": battlefield_name,
            "battlefield_definition_cn": battlefield_definition,
            "candidate_source_json": candidate_sources,
            "candidate_source_count": len(candidate_sources),
            "source_task_codes_json": source_tasks,
            "source_target_group_codes_json": source_groups,
            "source_claim_codes_json": source_claims,
            "source_param_codes_json": source_params,
            "source_topic_codes_json": source_topics,
            "candidate_initial_score": battlefield_score,
            "candidate_reason_cn": _candidate_reason_cn(candidate_status, battlefield_name, business_parts),
            "candidate_status": candidate_status,
            "reject_reason_json": {"reason_cn": "任务、客群、卖点、参数、评论与市场验证不足"} if candidate_status == M11BattlefieldCandidateStatus.REJECTED else {},
            "missing_signals_json": missing_signals,
            "risk_flags_json": risk_flags,
            "evidence_ids": evidence_ids,
            "evidence_matrix_refs_json": matrix_refs,
            "input_fingerprint": input_fingerprint,
            "result_hash": stable_hash(
                {"candidate_status": candidate_status, "score": battlefield_score, "sources": candidate_sources},
                version="m11_candidate_result_v1",
            ),
            "processing_status": _processing_status(candidate_status, risk.review_issues),
            "review_required": bool(risk.review_issues),
            "review_status": "review_required" if risk.review_issues else "auto_pass",
            "review_reason_json": {"issues": list(risk.review_issues)},
        }
        score_payload = {
            **common,
            "sku_battlefield_score_id": score_id,
            "sku_battlefield_candidate_id": candidate_id,
            "battlefield_code": battlefield_code,
            "battlefield_name_cn": battlefield_name,
            "battlefield_definition_cn": battlefield_definition,
            "semantic_score": semantic_score,
            "market_score": market_score,
            "core_task_score": task_score,
            "target_group_score": target_group_score,
            "core_claim_combo_score": claim_score,
            "core_param_capability_score": param_score,
            "comment_support_score": comment_score,
            "pain_point_risk_score": _decimal(domain_evidence[M11BattlefieldEvidenceDomain.COMMENT].risk_json.get("pain_point_risk_score")),
            "price_position_fit": price_fit,
            "sales_validation_score": sales_validation,
            "sales_amount_validation_score": sales_amount_validation,
            "channel_fit_score": channel_fit,
            "trend_signal_score": trend_signal,
            "comparable_pool_strength": pool_strength,
            "raw_battlefield_score": raw_score,
            "risk_penalty": risk.penalty,
            "battlefield_score": battlefield_score,
            "relation_level": relation_level,
            "relation_reason_json": _relation_reason_json(relation_level, semantic_score, market_score, coverage, risk),
            "competitor_selection_role": selection_role,
            "competitor_selection_role_cn": _selection_role_cn(selection_role),
            "sample_sufficiency": _sample_sufficiency(domain_evidence[M11BattlefieldEvidenceDomain.MARKET]),
            "confidence": confidence,
            "confidence_level": confidence_level,
            "evidence_domain_count": int(coverage["positive_domain_count"]),
            "effective_domain_json": coverage,
            "score_breakdown_json": {
                "semantic": float(semantic_score),
                "market": float(market_score),
                "market_pool_fit": float(market_pool_fit),
                "product_anchor": float(product_anchor_score),
                "value_theme": float(value_theme_score),
                "task_group_fit": float(task_group_fit_score),
                "market_performance": float(market_performance_score),
                "task": float(task_score),
                "target_group": float(target_group_score),
                "claim": float(claim_score),
                "param": float(param_score),
                "comment": float(comment_score),
                "service_side": float(service_score),
                "formula": "market_pool_fit*0.25 + product_anchor*0.30 + value_theme*0.15 + task_group_fit*0.10 + comment*0.10 + market_performance*0.10 - risk_penalty",
                "formula_version": "m11_battlefield_v2_size_price_pool",
                "market_pool_key": market_parts.get("market_pool_key"),
                "screen_size_class": market_parts.get("screen_size_class"),
                "price_position": market_parts.get("price_position"),
                "product_anchor_groups": market_parts.get("product_anchor_groups") or [],
            },
            "cap_rule_applied_json": list(risk.caps),
            "missing_signals_json": missing_signals,
            "risk_flags_json": risk_flags,
            "business_reason_cn": business_reason,
            "business_reason_parts_json": business_parts,
            "next_module_payload_json": {
                "source_module": "M11",
                "battlefield_code": battlefield_code,
                "battlefield_name_cn": battlefield_name,
                "relation_level": relation_level.value,
                "competitor_selection_role": selection_role.value,
                "battlefield_score": float(battlefield_score),
                "battlefield_v2": _battlefield_v2_payload(battlefield_code, context.battlefield),
                "market_pool_key": market_parts.get("market_pool_key"),
                "screen_size_class": market_parts.get("screen_size_class"),
                "product_anchor_score": float(product_anchor_score),
            },
            "evidence_ids": evidence_ids,
            "evidence_matrix_refs_json": matrix_refs,
            "input_fingerprint": input_fingerprint,
            "result_hash": stable_hash(
                {
                    "battlefield_code": battlefield_code,
                    "battlefield_score": battlefield_score,
                    "relation_level": relation_level,
                    "selection_role": selection_role,
                    "confidence": confidence,
                    "business_parts": business_parts,
                },
                version="m11_score_result_v1",
            ),
            "processing_status": _processing_status(candidate_status, risk.review_issues),
            "review_required": bool(risk.review_issues),
            "review_status": "review_required" if risk.review_issues else "auto_pass",
            "review_reason_json": {"issues": list(risk.review_issues)},
        }
        breakdowns = _breakdown_records(
            context=context,
            score_id=score_id,
            battlefield_name=battlefield_name,
            domain_evidence=domain_evidence,
            risk=risk,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        review_issues = _review_issue_records(
            context=context,
            candidate_id=candidate_id,
            score_id=score_id,
            battlefield_name=battlefield_name,
            issues=risk.review_issues,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        return M11BattlefieldBuildResult(
            candidate=M11SkuBattlefieldCandidateRecord(**candidate_payload),
            score=M11SkuBattlefieldScoreRecord(**score_payload),
            breakdowns=breakdowns,
            review_issues=review_issues,
        )

    def _blocked_battlefield(
        self,
        context: _BattlefieldScoreContext,
        *,
        blocked_reason: str,
        issue_type: str,
    ) -> M11BattlefieldBuildResult:
        battlefield_code = str(context.battlefield["battlefield_code"])
        battlefield_name = str(context.battlefield["battlefield_name"])
        battlefield_definition = str(context.battlefield["definition"])
        common = _common_output_fields(context)
        input_fingerprint = stable_hash(
            {
                "profile_hash": context.bundle.profile.profile_hash,
                "feature_view_hash": _feature_view_hash(context.bundle),
                "task_score_fingerprint": context.bundle.task_score_fingerprint,
                "target_group_score_fingerprint": context.bundle.target_group_score_fingerprint,
                "battlefield_seed_hash": context.seed.seed_hash,
                "battlefield_definition_hash": context.battlefield_definition_hash,
                "battlefield_code": battlefield_code,
                "blocked": blocked_reason,
            },
            version="m11_battlefield_input_v1",
        )
        candidate_id = _record_id("m11c", context.batch_id, context.bundle.profile.sku_code, battlefield_code, context.seed.seed_hash)
        score_id = _record_id("m11s", context.batch_id, context.bundle.profile.sku_code, battlefield_code, context.seed.seed_hash)
        issue = {
            "issue_type": issue_type,
            "reason_cn": blocked_reason,
            "severity": "blocking",
            "suggestion_cn": "先补齐 M08/M09/M10 上游结果，再重新运行 M11。",
        }
        candidate = M11SkuBattlefieldCandidateRecord(
            **{
                **common,
                "sku_battlefield_candidate_id": candidate_id,
                "battlefield_code": battlefield_code,
                "battlefield_name_cn": battlefield_name,
                "battlefield_definition_cn": battlefield_definition,
                "candidate_status": M11BattlefieldCandidateStatus.BLOCKED,
                "candidate_source_json": [],
                "candidate_source_count": 0,
                "source_task_codes_json": _source_task_codes(context.battlefield),
                "source_target_group_codes_json": list(context.seed.target_groups_by_battlefield.get(battlefield_code, ())),
                "source_claim_codes_json": _source_claim_codes(context.battlefield),
                "source_param_codes_json": _source_param_codes(context.battlefield),
                "source_topic_codes_json": _source_topic_codes(context.battlefield),
                "candidate_initial_score": D0,
                "candidate_reason_cn": blocked_reason,
                "missing_signals_json": [{"domain": "upstream", "reason_cn": blocked_reason}],
                "risk_flags_json": [issue],
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(issue, version="m11_candidate_result_v1"),
                "processing_status": "blocked",
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {"issues": [issue]},
            }
        )
        score = M11SkuBattlefieldScoreRecord(
            **{
                **common,
                "sku_battlefield_score_id": score_id,
                "sku_battlefield_candidate_id": candidate_id,
                "battlefield_code": battlefield_code,
                "battlefield_name_cn": battlefield_name,
                "battlefield_definition_cn": battlefield_definition,
                "relation_level": M11BattlefieldRelationLevel.BLOCKED,
                "competitor_selection_role": M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH,
                "competitor_selection_role_cn": _selection_role_cn(M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH),
                "confidence_level": Core3ConfidenceLevel.UNKNOWN,
                "business_reason_cn": blocked_reason,
                "business_reason_parts_json": {"待复核点": blocked_reason},
                "missing_signals_json": [{"domain": "upstream", "reason_cn": blocked_reason}],
                "risk_flags_json": [issue],
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(issue, version="m11_score_result_v1"),
                "processing_status": "blocked",
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {"issues": [issue]},
            }
        )
        empty_domains = {
            domain: M11BattlefieldDomainEvidence(
                domain=domain,
                support_level=M11BattlefieldSupportLevel.MISSING,
                score=D0,
                weight=_domain_weight(domain),
                reason_cn=blocked_reason if domain == M11BattlefieldEvidenceDomain.RISK else "上游输入不足，暂无法判断。",
            )
            for domain in (
                M11BattlefieldEvidenceDomain.TASK,
                M11BattlefieldEvidenceDomain.TARGET_GROUP,
                M11BattlefieldEvidenceDomain.CLAIM,
                M11BattlefieldEvidenceDomain.PARAM,
                M11BattlefieldEvidenceDomain.COMMENT,
                M11BattlefieldEvidenceDomain.MARKET,
                M11BattlefieldEvidenceDomain.SERVICE,
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
            battlefield_name=battlefield_name,
            domain_evidence=empty_domains,
            risk=risk,
            common=common,
            input_fingerprint=input_fingerprint,
        )
        review_issues = _review_issue_records(
            context=context,
            candidate_id=candidate_id,
            score_id=score_id,
            battlefield_name=battlefield_name,
            issues=(issue,),
            common=common,
            input_fingerprint=input_fingerprint,
        )
        return M11BattlefieldBuildResult(candidate=candidate, score=score, breakdowns=breakdowns, review_issues=review_issues)

    def _build_portfolios(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        seed: M11BattlefieldSeed,
        battlefield_definition_hash: str,
        battlefields: Sequence[Mapping[str, Any]],
        input_bundles: Sequence[M11InputBundle],
        scores: Sequence[M11SkuBattlefieldScoreRecord],
    ) -> list[M11SkuBattlefieldPortfolioRecord]:
        scores_by_sku: dict[str, list[M11SkuBattlefieldScoreRecord]] = defaultdict(list)
        for score in scores:
            scores_by_sku[score.sku_code].append(score)
        portfolios: list[M11SkuBattlefieldPortfolioRecord] = []
        bundles_by_sku = {bundle.profile.sku_code: bundle for bundle in input_bundles}
        battlefield_by_code = {str(item.get("battlefield_code") or ""): item for item in battlefields}
        relation_value = lambda item: str(getattr(item.relation_level, "value", item.relation_level))
        role_value = lambda item: str(getattr(item.competitor_selection_role, "value", item.competitor_selection_role))
        for sku_code, sku_scores in sorted(scores_by_sku.items()):
            bundle = bundles_by_sku[sku_code]
            sorted_scores = sorted(sku_scores, key=lambda item: (item.battlefield_score, item.confidence), reverse=True)
            product_scores = [
                item
                for item in sorted_scores
                if _score_allocation_eligible(item, battlefield_by_code.get(item.battlefield_code))
                and relation_value(item) != M11BattlefieldRelationLevel.BLOCKED.value
                and item.battlefield_score > D0
            ]
            main_scores = product_scores[:1]
            main_score = main_scores[0].battlefield_score if main_scores else D0
            secondary_scores = [
                item
                for item in product_scores[1:]
                if item.battlefield_score >= Decimal("0.4500") and (main_score <= D0 or item.battlefield_score >= main_score * Decimal("0.6500"))
            ][:2]
            selected_for_allocation = [*main_scores, *secondary_scores]
            weights = _portfolio_allocation_weights(selected_for_allocation)
            opportunity_scores = [
                item
                for item in product_scores
                if item not in selected_for_allocation and item.battlefield_score >= Decimal("0.3000")
            ][:3]
            weak_scores = [
                item
                for item in product_scores
                if item not in selected_for_allocation and item not in opportunity_scores
            ]
            main = [
                _portfolio_item(
                    item,
                    relation_level="main",
                    allocation_role="main_battlefield",
                    allocation_weight=weights.get(item.battlefield_code, D0),
                    allocation_eligible=True,
                )
                for item in main_scores
            ]
            secondary = [
                _portfolio_item(
                    item,
                    relation_level="secondary",
                    allocation_role="secondary_battlefield",
                    allocation_weight=weights.get(item.battlefield_code, D0),
                    allocation_eligible=True,
                )
                for item in secondary_scores
            ]
            opportunity = [
                _portfolio_item(item, relation_level="opportunity", allocation_role="opportunity_battlefield", allocation_weight=D0)
                for item in opportunity_scores
            ]
            weak = [
                _portfolio_item(item, relation_level="weak", allocation_role="weak_battlefield", allocation_weight=D0)
                for item in weak_scores
            ]
            insufficient = [
                _portfolio_item(item, allocation_weight=D0)
                for item in sorted_scores
                if relation_value(item)
                in {
                    M11BattlefieldRelationLevel.INSUFFICIENT.value,
                    M11BattlefieldRelationLevel.BLOCKED.value,
                }
                or not _score_allocation_eligible(item, battlefield_by_code.get(item.battlefield_code))
            ]
            primary_codes = [str(item["battlefield_code"]) for item in main]
            risk_flags: list[dict[str, Any] | str] = []
            if not primary_codes:
                risk_flags.append({"issue_type": "no_v2_product_battlefield", "reason_cn": "没有可分配的产品战场，需检查产品锚点和市场池结果。"})
            secondary_codes = [str(item["battlefield_code"]) for item in secondary]
            opportunity_codes = [str(item["battlefield_code"]) for item in opportunity]
            service_context = [
                _portfolio_item(item, relation_level=relation_value(item), allocation_role="context_only", allocation_weight=D0)
                for item in sorted_scores
                if role_value(item) == M11CompetitorSelectionRole.RISK_OR_SERVICE_CONTEXT.value
                or not _score_allocation_eligible(item, battlefield_by_code.get(item.battlefield_code))
            ]
            confidence = _round4(_average([item.confidence for item in sorted_scores if relation_value(item) != M11BattlefieldRelationLevel.BLOCKED.value]))
            evidence_ids = _dedupe([evidence_id for item in sorted_scores for evidence_id in item.evidence_ids])[:120]
            input_fingerprint = stable_hash(
                {
                    "profile_hash": bundle.profile.profile_hash,
                    "feature_view_hash": _feature_view_hash(bundle),
                    "task_score_fingerprint": bundle.task_score_fingerprint,
                    "target_group_score_fingerprint": bundle.target_group_score_fingerprint,
                    "battlefield_seed_hash": seed.seed_hash,
                    "battlefield_definition_hash": battlefield_definition_hash,
                    "score_hashes": [item.result_hash for item in sorted_scores],
                    "rule_version": rule_version,
                },
                version="m11_battlefield_portfolio_input_v1",
            )
            common = {
                "project_id": bundle.profile.project_id,
                "category_code": bundle.profile.category_code,
                "batch_id": batch_id,
                "run_id": run_id,
                "module_run_id": module_run_id,
                "sku_signal_profile_id": bundle.profile.sku_signal_profile_id,
                "sku_downstream_feature_view_id": bundle.feature_view.sku_downstream_feature_view_id if bundle.feature_view else None,
                "sku_code": bundle.profile.sku_code,
                "model_code": (bundle.profile.sku_master_json or {}).get("model_code"),
                "model_name": bundle.profile.model_name,
                "brand_name": bundle.profile.brand_name,
                "rule_version": rule_version,
                "battlefield_seed_version": CORE3_M11_SEED_VERSION,
                "battlefield_seed_file_version": seed.file_version,
                "battlefield_seed_hash": seed.seed_hash,
                "profile_hash": bundle.profile.profile_hash,
                "feature_view_hash": _feature_view_hash(bundle),
                "task_score_fingerprint": bundle.task_score_fingerprint,
                "target_group_score_fingerprint": bundle.target_group_score_fingerprint,
            }
            primary_names = [item["battlefield_name_cn"] for item in [*main, *secondary][:3]]
            context_cn = "、".join(primary_names) if primary_names else "暂无稳定主战场"
            payload = {
                **common,
                "sku_battlefield_portfolio_id": _record_id("m11p", batch_id, sku_code, seed.seed_hash),
                "main_battlefields_json": main,
                "secondary_battlefields_json": secondary,
                "opportunity_battlefields_json": opportunity,
                "weak_battlefields_json": weak,
                "insufficient_battlefields_json": insufficient,
                "primary_competitor_search_context_cn": f"{sku_code} 当前竞品召回应优先围绕：{context_cn}。",
                "primary_search_battlefield_codes_json": primary_codes,
                "secondary_search_battlefield_codes_json": secondary_codes,
                "opportunity_monitoring_codes_json": opportunity_codes,
                "risk_or_service_context_json": service_context,
                "portfolio_confidence": confidence,
                "portfolio_risk_flags_json": risk_flags,
                "battlefield_score_refs_json": [
                    {
                        "sku_battlefield_score_id": item.sku_battlefield_score_id,
                        "battlefield_code": item.battlefield_code,
                        "battlefield_score": float(item.battlefield_score),
                        "relation_level": item.relation_level,
                        "result_hash": item.result_hash,
                    }
                    for item in sorted_scores
                ],
                "evidence_ids": evidence_ids,
                "input_fingerprint": input_fingerprint,
                "result_hash": stable_hash(
                    {
                        "main": main,
                        "secondary": secondary,
                        "opportunity": opportunity,
                        "primary_codes": primary_codes,
                        "secondary_codes": secondary_codes,
                        "risk_flags": risk_flags,
                    },
                    version="m11_portfolio_result_v1",
                ),
                "review_required": bool(risk_flags),
                "review_status": "review_required" if risk_flags else "auto_pass",
                "review_reason_json": {"issues": risk_flags},
            }
            portfolios.append(M11SkuBattlefieldPortfolioRecord(**payload))
        return portfolios


def _score_task_domain(battlefield: Mapping[str, Any], bundle: M11InputBundle) -> M11BattlefieldDomainEvidence:
    source_codes = _source_task_codes(battlefield)
    scores_by_code = {row.task_code: row for row in bundle.task_scores}
    matched: list[dict[str, Any]] = []
    values: list[Decimal] = []
    for task_code in source_codes:
        row = scores_by_code.get(task_code)
        if row is None:
            continue
        value = _clamp(_decimal(row.task_score) * _task_relation_factor(str(row.relation_level)))
        matched.append(
            {
                "task_code": task_code,
                "task_name_cn": row.task_name_cn,
                "relation_level": row.relation_level,
                "task_score": float(row.task_score or 0),
                "weighted_support": float(value),
                "review_required": bool(row.review_required),
            }
        )
        values.append(value)
    if not values:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.TASK,
            support_level=M11BattlefieldSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.TASK),
            reason_cn="源用户任务未形成可用关系，不能支撑战场判断。",
            source_feature_refs=[{"feature": "M09.task_scores", "expected": source_codes}],
        )
    score = _round4(sum(values) / Decimal(max(len(source_codes), 1)))
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.TASK,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.TASK),
        reason_cn=f"命中 {len(matched)} 个源用户任务，主要任务为 {', '.join(item['task_name_cn'] or item['task_code'] for item in matched[:3])}。",
        evidence_ids=_task_evidence_ids(bundle, source_codes),
        source_feature_refs=matched,
        risk_json={"source_task_count": len(source_codes), "matched_task_count": len(matched)},
    )


def _score_target_group_domain(
    battlefield: Mapping[str, Any],
    bundle: M11InputBundle,
    seed: M11BattlefieldSeed,
) -> M11BattlefieldDomainEvidence:
    battlefield_code = str(battlefield.get("battlefield_code") or "")
    source_codes = list(seed.target_groups_by_battlefield.get(battlefield_code, ()))
    scores_by_code = {row.target_group_code: row for row in bundle.target_group_scores}
    matched: list[dict[str, Any]] = []
    values: list[Decimal] = []
    for group_code in source_codes:
        row = scores_by_code.get(group_code)
        if row is None:
            continue
        value = _clamp(_decimal(row.target_group_score) * _group_relation_factor(str(row.relation_level)))
        matched.append(
            {
                "target_group_code": group_code,
                "target_group_name_cn": row.target_group_name_cn,
                "relation_level": row.relation_level,
                "target_group_score": float(row.target_group_score or 0),
                "weighted_support": float(value),
                "review_required": bool(row.review_required),
            }
        )
        values.append(value)
    if not values:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.TARGET_GROUP,
            support_level=M11BattlefieldSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.TARGET_GROUP),
            reason_cn="目标客群未形成可用关系，不能支撑战场判断。",
            source_feature_refs=[{"feature": "M10.target_group_scores", "expected": source_codes}],
        )
    score = _round4(sum(values) / Decimal(max(len(source_codes), 1)))
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.TARGET_GROUP,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.TARGET_GROUP),
        reason_cn=f"命中 {len(matched)} 个目标客群，主要客群为 {', '.join(item['target_group_name_cn'] or item['target_group_code'] for item in matched[:3])}。",
        evidence_ids=_target_group_evidence_ids(bundle, source_codes),
        source_feature_refs=matched,
        risk_json={"source_target_group_count": len(source_codes), "matched_target_group_count": len(matched)},
    )


def _score_claim_domain(
    battlefield: Mapping[str, Any],
    payload: Mapping[str, Any],
    bundle: M11InputBundle,
) -> M11BattlefieldDomainEvidence:
    source_codes = set(_source_claim_codes(battlefield))
    claim_summary = dict(payload.get("claim_activation_summary") or {})
    top_claims = list(claim_summary.get("top_claims") or [])
    matched = [
        item
        for item in top_claims
        if str(item.get("claim_code_hint") or item.get("claim_code") or "") in source_codes
    ]
    if not matched:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.CLAIM,
            support_level=M11BattlefieldSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.CLAIM),
            reason_cn="核心卖点尚未形成该战场的结构化支撑。",
            source_feature_refs=[{"feature": "claim_activation_summary.top_claims", "expected": sorted(source_codes)}],
        )
    values = [_claim_activation_value(item) for item in matched]
    score = _round4(sum(values) / Decimal(max(len(source_codes), 1)))
    names = [str(item.get("claim_name") or item.get("claim_code_hint")) for item in matched[:4]]
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.CLAIM,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.CLAIM),
        reason_cn=f"核心卖点命中 {len(matched)} 项，代表卖点为 {', '.join(names)}。",
        evidence_ids=_matrix_evidence_ids(bundle, "claim", ("structured_claim", "final_claim_activation")),
        source_feature_refs=[
            {
                "claim_code": str(item.get("claim_code_hint") or item.get("claim_code")),
                "claim_name": item.get("claim_name"),
                "activation_level": item.get("activation_level"),
                "final_activation_score": float(_decimal(item.get("final_activation_score"))),
                "confidence": float(_decimal(item.get("confidence"))),
            }
            for item in matched[:8]
        ],
        risk_json={"expected_claim_count": len(source_codes), "matched_claim_count": len(matched)},
    )


def _score_param_domain(
    battlefield: Mapping[str, Any],
    payload: Mapping[str, Any],
    bundle: M11InputBundle,
) -> M11BattlefieldDomainEvidence:
    source_codes = _source_param_codes(battlefield)
    param_payload = dict(payload.get("core_params") or {})
    param_values = dict(param_payload.get("param_values") or {})
    matched: list[dict[str, Any]] = []
    values: list[Decimal] = []
    for param_code in source_codes:
        item = dict(param_values.get(param_code) or {})
        if not item:
            continue
        value = _param_support_value(param_code, item)
        if value <= D0:
            continue
        matched.append(
            {
                "param_code": param_code,
                "param_name": item.get("param_name") or param_code,
                "value": item.get("value"),
                "numeric_value": item.get("numeric_value"),
                "unit": item.get("unit"),
                "support_score": float(value),
                "confidence": float(_decimal(item.get("confidence"))),
            }
        )
        values.append(value)
    if not values:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.PARAM,
            support_level=M11BattlefieldSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.PARAM),
            reason_cn="关键参数缺失或不足，无法形成该战场硬规格支撑。",
            source_feature_refs=[{"feature": "core_params.param_values", "expected": source_codes}],
        )
    score = _round4(sum(values) / Decimal(max(len(source_codes), 1)))
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.PARAM,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.PARAM),
        reason_cn=f"关键参数命中 {len(matched)} 项，代表参数为 {', '.join(item['param_name'] for item in matched[:4])}。",
        evidence_ids=_matrix_evidence_ids(bundle, "param", ("core_params",)),
        source_feature_refs=matched[:8],
        risk_json={"expected_param_count": len(source_codes), "matched_param_count": len(matched)},
    )


def _score_comment_domain(
    battlefield: Mapping[str, Any],
    payload: Mapping[str, Any],
    bundle: M11InputBundle,
) -> M11BattlefieldDomainEvidence:
    comment_summary = dict(payload.get("comment_signal_summary") or {})
    type_summary = dict(comment_summary.get("signal_type_summary") or {})
    battlefield_summary = dict(type_summary.get("battlefield_support") or {})
    claim_summary = dict(type_summary.get("claim_validation") or {})
    battlefield_code = str(battlefield.get("battlefield_code") or "")
    target_hints = [str(item) for item in battlefield_summary.get("target_code_hints") or []]
    top_phrases = [str(item) for item in battlefield_summary.get("top_phrases") or []]
    claim_phrases = [str(item) for item in claim_summary.get("top_phrases") or []]
    keyword_hit = _keyword_hit(battlefield, [*top_phrases, *claim_phrases])
    if battlefield_code not in target_hints and not keyword_hit:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.COMMENT,
            support_level=M11BattlefieldSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.COMMENT),
            reason_cn="评论中暂未形成该战场的稳定体验线索。",
            source_feature_refs=[{"feature": "comment_signal_summary.battlefield_support", "target_code_hints": target_hints[:12]}],
        )
    strong_count = int(battlefield_summary.get("strong_count") or 0)
    medium_count = int(battlefield_summary.get("medium_count") or 0)
    signal_count = int(battlefield_summary.get("signal_count") or 0)
    score = Decimal("0.8500") if strong_count else Decimal("0.6500")
    if keyword_hit and battlefield_code not in target_hints:
        score = Decimal("0.4500")
    if signal_count <= 1:
        score = min(score, Decimal("0.5500"))
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.COMMENT,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.COMMENT),
        reason_cn=f"评论出现该战场体验线索，强信号 {strong_count} 条、中信号 {medium_count} 条。",
        evidence_ids=_matrix_evidence_ids(bundle, "comment", ("battlefield_support", "claim_validation")),
        source_feature_refs=[
            {
                "feature": "comment_signal_summary.battlefield_support",
                "target_code_hints": target_hints[:12],
                "top_phrases": top_phrases[:8],
                "claim_phrases": claim_phrases[:8],
            }
        ],
        risk_json={"signal_count": signal_count, "pain_point_risk_score": D0},
    )


def _score_market_domain(
    battlefield: Mapping[str, Any],
    payload: Mapping[str, Any],
    bundle: M11InputBundle,
) -> M11BattlefieldDomainEvidence:
    profile = bundle.profile
    market_summary = dict(profile.market_summary_json or {})
    business_index = dict(profile.business_signal_index_json or {})
    pool_summary = dict(profile.comparable_pool_summary_json or {})
    market_signal_summary = dict(payload.get("market_signal_summary") or {})
    battlefield_code = str(battlefield.get("battlefield_code") or "")
    price_band = str(market_summary.get("price_band_category") or market_summary.get("price_band_size") or "")
    screen_size = _decimal(market_summary.get("screen_size_inch"))
    volume = _decimal(market_summary.get("sales_volume_total"))
    amount = _decimal(market_summary.get("sales_amount_total"))
    sample_status = str(market_summary.get("sample_status") or pool_summary.get("sample_status") or "")
    signal_counts = dict(market_signal_summary.get("signal_code_counts") or {})
    same_pool = dict(business_index.get("same_pool_position") or {})
    screen_size_class = str(market_summary.get("screen_size_class") or business_index.get("screen_size_class") or "")
    market_pool_key = str(market_summary.get("market_pool_key") or business_index.get("market_pool_key") or "")
    same_pool_price_percentile = _decimal(
        market_summary.get("same_pool_price_percentile")
        or market_summary.get("price_percentile_in_pool")
        or same_pool.get("price_percentile")
    )
    same_pool_volume_percentile = _decimal(
        market_summary.get("same_pool_volume_percentile")
        or market_summary.get("sales_percentile_in_pool")
        or same_pool.get("volume_percentile")
    )
    same_pool_amount_percentile = _decimal(
        market_summary.get("same_pool_amount_percentile")
        or market_summary.get("amount_percentile_in_pool")
        or same_pool.get("amount_percentile")
    )
    price_per_inch_percentile = _decimal(market_summary.get("price_per_inch_percentile") or same_pool.get("price_per_inch_percentile"))
    same_pool_count = int(market_summary.get("same_pool_sku_count") or same_pool.get("sample_count") or 0)
    price_position = _price_position_from_percentile(same_pool_price_percentile)
    price_fit = _market_price_fit_score(battlefield_code, price_position, price_per_inch_percentile, battlefield=battlefield)
    if price_fit <= D0:
        price_fit = _price_fit_score(battlefield_code, price_band, screen_size)
    sales_validation = _percentile_validation_score(same_pool_volume_percentile) or (Decimal("0.7000") if volume > 0 else D0)
    sales_amount_validation = _percentile_validation_score(same_pool_amount_percentile) or (Decimal("0.7000") if amount > 0 else D0)
    channel_fit = Decimal("0.5500") if market_summary.get("main_platform") or market_summary.get("main_channel_type") else D0
    trend_signal = Decimal("0.5500") if signal_counts else D0
    pool_count = int(pool_summary.get("pool_count") or 0)
    pool_strength = _pool_strength(max(pool_count, same_pool_count))
    market_pool_fit = _market_pool_fit_score(
        battlefield_code=battlefield_code,
        screen_size_class=screen_size_class,
        price_position=price_position,
        sample_count=max(pool_count, same_pool_count),
        battlefield=battlefield,
    )
    anchor_fit, anchor_payload = _product_anchor_fit_score(battlefield_code, business_index, battlefield=battlefield)
    score = _round4(
        market_pool_fit * Decimal("0.3000")
        + price_fit * Decimal("0.1500")
        + sales_validation * Decimal("0.2000")
        + sales_amount_validation * Decimal("0.1000")
        + channel_fit * Decimal("0.0500")
        + trend_signal * Decimal("0.0500")
        + pool_strength * Decimal("0.1000")
        + anchor_fit * Decimal("0.0500")
    )
    if score <= D0:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.MARKET,
            support_level=M11BattlefieldSupportLevel.MISSING,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.MARKET),
            reason_cn="缺少价格、销量、渠道、趋势或可比池信息，暂无法做市场验证。",
            source_feature_refs=[{"feature": "M08.market_summary"}],
            risk_json={"sample_status": sample_status},
        )
    reason = (
        f"市场池适配 {market_pool_fit:.2f}、价位适配 {price_fit:.2f}、销量验证 {sales_validation:.2f}、"
        f"销额验证 {sales_amount_validation:.2f}，同池样本 {max(pool_count, same_pool_count)} 个。"
    )
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.MARKET,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.MARKET),
        reason_cn=reason,
        evidence_ids=_matrix_evidence_ids(bundle, "market", ("price", "sales", "trend")) + _matrix_evidence_ids(bundle, "pool", ("same_size", "same_price_band", "size_price_band")),
        source_feature_refs=[
            {
                "feature": "M08.market_summary",
                "price_band": price_band,
                "screen_size_inch": float(screen_size),
                "screen_size_class": screen_size_class,
                "market_pool_key": market_pool_key,
                "price_position": price_position,
                "pool_count": pool_count,
                "same_pool_sku_count": same_pool_count,
                "market_signal_count": market_signal_summary.get("market_signal_count", 0),
                "product_anchor_groups": anchor_payload.get("matched_groups") or [],
            }
        ],
        risk_json={
            "sample_status": sample_status,
            "price_position_fit": price_fit,
            "sales_validation_score": sales_validation,
            "sales_amount_validation_score": sales_amount_validation,
            "channel_fit_score": channel_fit,
            "trend_signal_score": trend_signal,
            "comparable_pool_strength": pool_strength,
            "market_pool_fit_score": market_pool_fit,
            "product_anchor_fit_score": anchor_fit,
            "product_anchor_groups": anchor_payload.get("matched_groups") or [],
            "product_anchor_required_groups": anchor_payload.get("required_groups") or [],
            "product_anchor_source_statuses": anchor_payload.get("source_statuses") or [],
            "market_pool_key": market_pool_key,
            "screen_size_class": screen_size_class,
            "price_position": price_position,
            "same_pool_price_percentile": same_pool_price_percentile,
            "same_pool_volume_percentile": same_pool_volume_percentile,
            "same_pool_amount_percentile": same_pool_amount_percentile,
            "price_per_inch_percentile": price_per_inch_percentile,
            "same_pool_sku_count": same_pool_count,
            "market_missing": volume <= 0 and amount <= 0,
            "pool_count": pool_count,
        },
    )


def _score_service_domain(
    battlefield: Mapping[str, Any],
    payload: Mapping[str, Any],
    bundle: M11InputBundle,
) -> M11BattlefieldDomainEvidence:
    profile_summary = dict(bundle.profile.comment_signal_summary_json or {})
    view_summary = dict(payload.get("comment_signal_summary") or {})
    type_summary = dict(profile_summary.get("signal_type_summary") or view_summary.get("signal_type_summary") or {})
    service_summary = dict(type_summary.get("service_signal") or {})
    signal_count = int(service_summary.get("signal_count") or 0)
    strong_count = int(service_summary.get("strong_count") or 0)
    battlefield_code = str(battlefield.get("battlefield_code") or "")
    if signal_count <= 0:
        return M11BattlefieldDomainEvidence(
            domain=M11BattlefieldEvidenceDomain.SERVICE,
            support_level=M11BattlefieldSupportLevel.NOT_APPLICABLE,
            score=D0,
            weight=_domain_weight(M11BattlefieldEvidenceDomain.SERVICE),
            reason_cn="服务/安装暂无稳定战场侧面线索。",
            source_feature_refs=[{"feature": "comment_signal_summary.service_signal"}],
        )
    score = Decimal("0.7000") if strong_count else Decimal("0.5000")
    if battlefield_code not in {"BF_SERVICE_ASSURANCE", "BF_DESIGN_HOME_FIT"}:
        score = min(score, Decimal("0.2500"))
    return M11BattlefieldDomainEvidence(
        domain=M11BattlefieldEvidenceDomain.SERVICE,
        support_level=_support_level(score),
        score=score,
        weight=_domain_weight(M11BattlefieldEvidenceDomain.SERVICE),
        reason_cn=f"服务/安装相关评论 {signal_count} 条，可作为服务保障或家居适配侧面。",
        evidence_ids=_matrix_evidence_ids(bundle, "comment", ("service_signal",)),
        source_feature_refs=[{"feature": "comment_signal_summary.service_signal", "signal_count": signal_count, "strong_count": strong_count}],
        risk_json={"service_side_only": True},
    )


def _evaluate_risk(
    context: _BattlefieldScoreContext,
    domain_evidence: Mapping[M11BattlefieldEvidenceDomain, M11BattlefieldDomainEvidence],
) -> _RiskEvaluation:
    issues: list[dict[str, Any]] = []
    caps: list[dict[str, Any]] = []
    penalty = D0
    battlefield_code = str(context.battlefield.get("battlefield_code") or "")
    counted_domains = {
        domain: evidence
        for domain, evidence in domain_evidence.items()
        if domain != M11BattlefieldEvidenceDomain.SERVICE and evidence.score >= Decimal("0.2500")
    }
    positive_domains = list(counted_domains)
    if positive_domains == [M11BattlefieldEvidenceDomain.COMMENT]:
        caps.append({"rule": "only_comment", "max_score": "0.4400", "reason_cn": "评论单域只能形成弱战场线索。"})
        issues.append(_issue(M11BattlefieldReviewIssueType.ONLY_COMMENT, "该战场主要来自评论线索，缺少任务、客群、卖点、参数或市场验证。"))
    if not positive_domains and domain_evidence[M11BattlefieldEvidenceDomain.SERVICE].score >= Decimal("0.2500"):
        max_score = "0.5900" if battlefield_code in {"BF_SERVICE_ASSURANCE", "BF_DESIGN_HOME_FIT"} else "0.3400"
        caps.append({"rule": "only_service", "max_score": max_score, "reason_cn": "服务单域不能作为产品核心战场依据。"})
        issues.append(_issue(M11BattlefieldReviewIssueType.ONLY_SERVICE, "该战场主要来自服务体验线索，需隔离为服务或家居侧面。"))
    if domain_evidence[M11BattlefieldEvidenceDomain.MARKET].score <= D0:
        caps.append({"rule": "market_missing", "max_score": "0.7400", "reason_cn": "缺少市场验证时不能升为主战场。"})
        issues.append(_issue(M11BattlefieldReviewIssueType.MARKET_MISSING, "缺少价格、销量或可比池市场验证，战场关系需要限制。", severity="info"))
    market_risk = dict(domain_evidence[M11BattlefieldEvidenceDomain.MARKET].risk_json or {})
    if market_risk.get("sample_status") in {"limited", "insufficient"}:
        penalty += Decimal("0.0300")
        issues.append(_issue(M11BattlefieldReviewIssueType.MARKET_LIMITED, "市场样本有限，战场判断需要带限制说明。"))
    if max(int(market_risk.get("pool_count") or 0), int(market_risk.get("same_pool_sku_count") or 0)) <= 0:
        issues.append(_issue(M11BattlefieldReviewIssueType.COMPARABLE_POOL_INSUFFICIENT, "可比池不足，后续候选召回需要谨慎。", severity="info"))
    v2_rule = _battlefield_v2_rule_for(battlefield_code, context.battlefield)
    migration_action = str(v2_rule.get("migration_action") or "")
    if migration_action in V2_NON_PRODUCT_ACTIONS:
        caps.append(
            {
                "rule": f"v2_{migration_action}",
                "max_score": "0.3400",
                "reason_cn": "新版定义将该维度作为客群/任务/产品锚点语境，不直接作为产品价值战场分配销量。",
                "merged_into": v2_rule.get("merged_into"),
            }
        )
        issues.append(
            _plain_issue(
                f"v2_{migration_action}_battlefield",
                "新版定义不允许该维度直接作为 SKU 主战场或辅战场，只能进入解释语境。",
                severity="info",
            )
        )
    if battlefield_code != SERVICE_BATTLEFIELD_CODE and v2_rule.get("anchor_groups") and _decimal(market_risk.get("product_anchor_fit_score")) <= D0:
        caps.append({"rule": "v2_product_anchor_missing", "max_score": "0.4900", "reason_cn": "缺少该战场要求的产品锚点，不能升为主战场。"})
        issues.append(_plain_issue("v2_product_anchor_missing", "该战场缺少参数或卖点锚点，只能作为弱线索或机会观察。"))
    if battlefield_code != SERVICE_BATTLEFIELD_CODE and _decimal(market_risk.get("market_pool_fit_score")) < Decimal("0.3000"):
        caps.append({"rule": "v2_market_pool_mismatch", "max_score": "0.5400", "reason_cn": "尺寸段或同池价位与该战场定义不匹配，不能升为主战场。"})
        issues.append(_plain_issue("v2_market_pool_mismatch", "SKU 所在尺寸价格池与该战场定义匹配不足，需要降级。", severity="info"))
    if domain_evidence[M11BattlefieldEvidenceDomain.CLAIM].score <= D0 and battlefield_code not in {"BF_SERVICE_ASSURANCE"}:
        penalty += Decimal("0.0200")
        issues.append(_issue(M11BattlefieldReviewIssueType.CLAIM_MISSING, "缺少该战场核心卖点激活，不能把战场解释为强产品优势。"))
    if domain_evidence[M11BattlefieldEvidenceDomain.PARAM].risk_json.get("matched_param_count", 0) == 0 and battlefield_code not in {"BF_SERVICE_ASSURANCE", "BF_DESIGN_HOME_FIT"}:
        penalty += Decimal("0.0100")
    source_task_codes = set(_source_task_codes(context.battlefield))
    inherited_task_reviews = [
        row
        for row in context.bundle.task_review_issues
        if row.task_code in source_task_codes and str(row.issue_severity) in {"warning", "blocking", "error", "high", "medium"}
    ]
    source_group_codes = set(context.seed.target_groups_by_battlefield.get(battlefield_code, ()))
    inherited_group_reviews = [
        row
        for row in context.bundle.target_group_review_issues
        if row.target_group_code in source_group_codes and str(row.issue_severity) in {"warning", "blocking", "error", "high", "medium"}
    ]
    if inherited_task_reviews or inherited_group_reviews:
        caps.append({"rule": "upstream_review", "max_score": "0.7400", "reason_cn": "源任务或客群存在复核问题，战场不能直接升为主战场。"})
        issues.append(_issue(M11BattlefieldReviewIssueType.UPSTREAM_REVIEW, "源任务或源客群存在复核问题，战场结论需继承降级。"))
    if battlefield_code == "BF_SERVICE_ASSURANCE":
        caps.append({"rule": "service_as_core_battlefield", "max_score": "0.5900", "reason_cn": "服务保障只进入风险/服务语境，不作为产品核心召回主战场。"})
        issues.append(_issue(M11BattlefieldReviewIssueType.SERVICE_AS_CORE_BATTLEFIELD, "服务保障战场默认不进入核心竞品主召回。", severity="info"))
    return _RiskEvaluation(penalty=_clamp(penalty), caps=tuple(caps), review_issues=tuple(_dedupe_issue_dicts(issues)))


def _breakdown_records(
    *,
    context: _BattlefieldScoreContext,
    score_id: str,
    battlefield_name: str,
    domain_evidence: Mapping[M11BattlefieldEvidenceDomain, M11BattlefieldDomainEvidence],
    risk: _RiskEvaluation,
    common: Mapping[str, Any],
    input_fingerprint: str,
) -> list[M11SkuBattlefieldEvidenceBreakdownRecord]:
    records: list[M11SkuBattlefieldEvidenceBreakdownRecord] = []
    breakdown_common = _without_profile_view_refs(common)
    battlefield_code = str(context.battlefield["battlefield_code"])
    for domain in CORE3_M11_EVIDENCE_DOMAINS:
        if domain in domain_evidence:
            evidence = domain_evidence[domain]
        elif domain == M11BattlefieldEvidenceDomain.RISK:
            evidence = M11BattlefieldDomainEvidence(
                domain=domain,
                support_level=M11BattlefieldSupportLevel.CONFLICT if risk.review_issues else M11BattlefieldSupportLevel.NOT_APPLICABLE,
                score=risk.penalty,
                weight=D0,
                reason_cn="；".join(item["reason_cn"] for item in risk.review_issues) or "未发现需要封顶或降级的风险。",
                risk_json={"caps": list(risk.caps), "issues": list(risk.review_issues)},
            )
        elif domain == M11BattlefieldEvidenceDomain.SEED:
            evidence = M11BattlefieldDomainEvidence(
                domain=domain,
                support_level=M11BattlefieldSupportLevel.STRONG,
                score=D1,
                weight=D0,
                reason_cn="价值战场本体来自固定 TV MVP seed，当前只作为推导框架，不直接代表 SKU 结论。",
                source_feature_refs=[{"battlefield_seed_version": context.seed.seed_version, "battlefield_seed_hash": context.seed.seed_hash}],
            )
        else:
            profile = context.bundle.profile
            evidence = M11BattlefieldDomainEvidence(
                domain=domain,
                support_level=_support_level(_decimal(profile.confidence)),
                score=_clamp(_decimal(profile.confidence)),
                weight=D0,
                reason_cn=f"M08 综合画像完整度 {float(profile.data_completeness_score or 0):.2f}，作为战场判断底层可信度参考。",
                evidence_ids=list(profile.representative_evidence_ids or [])[:20],
                source_feature_refs=[{"profile_hash": profile.profile_hash, "profile_status": profile.profile_status}],
            )
        weighted = _round4(evidence.score * evidence.weight)
        payload = {
            "sku_code": context.bundle.profile.sku_code,
            "battlefield_code": battlefield_code,
            "domain": domain.value,
            "score": evidence.score,
            "weight": evidence.weight,
            "input_fingerprint": input_fingerprint,
        }
        records.append(
            M11SkuBattlefieldEvidenceBreakdownRecord(
                **{
                    **breakdown_common,
                    "sku_battlefield_evidence_breakdown_id": _record_id(
                        "m11b",
                        context.batch_id,
                        context.bundle.profile.sku_code,
                        battlefield_code,
                        domain.value,
                        context.seed.seed_hash,
                    ),
                    "sku_battlefield_score_id": score_id,
                    "battlefield_code": battlefield_code,
                    "battlefield_name_cn": battlefield_name,
                    "evidence_domain": domain,
                    "support_level": evidence.support_level,
                    "domain_score": evidence.score,
                    "domain_weight": evidence.weight,
                    "weighted_score": weighted,
                    "evidence_count": len(evidence.evidence_ids),
                    "evidence_ids": evidence.evidence_ids[:120],
                    "source_feature_refs_json": evidence.source_feature_refs,
                    "domain_reason_cn": evidence.reason_cn,
                    "domain_risk_json": evidence.risk_json,
                    "input_fingerprint": input_fingerprint,
                    "result_hash": stable_hash(payload, version="m11_breakdown_result_v1"),
                    "review_required": domain == M11BattlefieldEvidenceDomain.RISK and bool(risk.review_issues),
                    "review_status": "review_required" if domain == M11BattlefieldEvidenceDomain.RISK and risk.review_issues else "auto_pass",
                    "review_reason_json": {"issues": list(risk.review_issues)} if domain == M11BattlefieldEvidenceDomain.RISK else {},
                }
            )
        )
    return records


def _review_issue_records(
    *,
    context: _BattlefieldScoreContext,
    candidate_id: str,
    score_id: str,
    battlefield_name: str,
    issues: Sequence[Mapping[str, Any]],
    common: Mapping[str, Any],
    input_fingerprint: str,
) -> list[M11SkuBattlefieldReviewIssueRecord]:
    records: list[M11SkuBattlefieldReviewIssueRecord] = []
    issue_common = _without_profile_view_refs(common)
    battlefield_code = str(context.battlefield["battlefield_code"])
    for issue in issues:
        issue_type = str(issue.get("issue_type") or M11BattlefieldReviewIssueType.SEED_GAP.value)
        payload = {
            "sku_code": context.bundle.profile.sku_code,
            "battlefield_code": battlefield_code,
            "issue_type": issue_type,
            "input_fingerprint": input_fingerprint,
        }
        records.append(
            M11SkuBattlefieldReviewIssueRecord(
                **{
                    **issue_common,
                    "sku_battlefield_review_issue_id": _record_id(
                        "m11r",
                        context.batch_id,
                        context.bundle.profile.sku_code,
                        battlefield_code,
                        issue_type,
                        context.seed.seed_hash,
                    ),
                    "sku_battlefield_score_id": score_id,
                    "sku_battlefield_candidate_id": candidate_id,
                    "battlefield_code": battlefield_code,
                    "battlefield_name_cn": battlefield_name,
                    "issue_type": issue_type,
                    "issue_severity": str(issue.get("severity") or "warning"),
                    "issue_status": "open",
                    "issue_reason_cn": str(issue.get("reason_cn") or "价值战场证据需要复核。"),
                    "issue_detail_json": dict(issue),
                    "affected_output_json": {"score_id": score_id, "candidate_id": candidate_id},
                    "evidence_ids": [],
                    "suggested_action_cn": str(issue.get("suggestion_cn") or "补充上游数据或业务复核后重新运行 M11。"),
                    "input_fingerprint": input_fingerprint,
                    "result_hash": stable_hash(payload, version="m11_review_issue_result_v1"),
                    "processing_status": "blocked" if issue.get("severity") == "blocking" else "warning",
                    "review_required": True,
                    "review_status": "review_required",
                    "review_reason_json": dict(issue),
                }
            )
        )
    return records


def _common_output_fields(context: _BattlefieldScoreContext) -> dict[str, Any]:
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
        "battlefield_seed_version": CORE3_M11_SEED_VERSION,
        "battlefield_seed_file_version": context.seed.file_version,
        "battlefield_seed_hash": context.seed.seed_hash,
        "profile_hash": profile.profile_hash,
        "feature_view_hash": _feature_view_hash(context.bundle),
        "task_score_fingerprint": context.bundle.task_score_fingerprint,
        "target_group_score_fingerprint": context.bundle.target_group_score_fingerprint,
    }


def _without_profile_view_refs(common: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in common.items()
        if key not in {"sku_signal_profile_id", "sku_downstream_feature_view_id"}
    }


def _source_task_codes(battlefield: Mapping[str, Any]) -> list[str]:
    return [str(code) for code in battlefield.get("core_task_codes") or battlefield.get("mapped_task_codes") or []]


def _source_claim_codes(battlefield: Mapping[str, Any]) -> list[str]:
    return [str(code) for code in battlefield.get("core_claim_codes") or battlefield.get("mapped_claim_codes") or []]


def _source_param_codes(battlefield: Mapping[str, Any]) -> list[str]:
    return [str(code) for code in battlefield.get("core_param_codes") or battlefield.get("mapped_param_codes") or []]


def _source_topic_codes(battlefield: Mapping[str, Any]) -> list[str]:
    return [str(code) for code in battlefield.get("comment_topic_codes") or battlefield.get("mapped_topic_codes") or []]


def _task_evidence_ids(bundle: M11InputBundle, source_task_codes: Sequence[str]) -> list[str]:
    source_codes = set(source_task_codes)
    ids: list[str] = []
    for row in bundle.task_breakdowns:
        if row.task_code in source_codes:
            ids.extend(str(item) for item in row.evidence_refs_json or [])
    return _dedupe(ids)[:120]


def _target_group_evidence_ids(bundle: M11InputBundle, source_group_codes: Sequence[str]) -> list[str]:
    source_codes = set(source_group_codes)
    ids: list[str] = []
    for row in bundle.target_group_breakdowns:
        if row.target_group_code in source_codes:
            ids.extend(str(item) for item in row.evidence_ids or [])
    return _dedupe(ids)[:120]


def _matrix_evidence_ids(bundle: M11InputBundle, domain: str, sub_domains: Sequence[str] = ()) -> list[str]:
    sub_domain_set = set(sub_domains)
    ids: list[str] = []
    for matrix in bundle.evidence_matrices:
        if matrix.domain != domain:
            continue
        if sub_domain_set and matrix.sub_domain not in sub_domain_set:
            continue
        ids.extend(str(item) for item in matrix.representative_evidence_ids or [])
    return _dedupe(ids)[:120]


def _domain_weight(domain: M11BattlefieldEvidenceDomain) -> Decimal:
    return {
        M11BattlefieldEvidenceDomain.TASK: Decimal("0.3000"),
        M11BattlefieldEvidenceDomain.TARGET_GROUP: Decimal("0.1500"),
        M11BattlefieldEvidenceDomain.CLAIM: Decimal("0.2500"),
        M11BattlefieldEvidenceDomain.PARAM: Decimal("0.2000"),
        M11BattlefieldEvidenceDomain.COMMENT: Decimal("0.1000"),
        M11BattlefieldEvidenceDomain.MARKET: Decimal("0.3000"),
        M11BattlefieldEvidenceDomain.SERVICE: Decimal("0.0000"),
    }.get(domain, D0)


def _task_relation_factor(relation_level: str) -> Decimal:
    return {
        "main": Decimal("1.0000"),
        "secondary": Decimal("0.7600"),
        "weak": Decimal("0.4600"),
        "insufficient": Decimal("0.0000"),
        "blocked": Decimal("0.0000"),
    }.get(relation_level, D0)


def _group_relation_factor(relation_level: str) -> Decimal:
    return {
        "main": Decimal("1.0000"),
        "secondary": Decimal("0.7600"),
        "weak": Decimal("0.4600"),
        "insufficient": Decimal("0.0000"),
        "blocked": Decimal("0.0000"),
    }.get(relation_level, D0)


def _claim_activation_value(item: Mapping[str, Any]) -> Decimal:
    score = _decimal(item.get("final_activation_score"))
    level_factor = {
        "high": Decimal("1.0000"),
        "medium": Decimal("0.7500"),
        "weak": Decimal("0.4500"),
        "inactive": Decimal("0.0000"),
        "blocked": Decimal("0.0000"),
    }.get(str(item.get("activation_level") or ""), Decimal("0.5000"))
    confidence = _decimal(item.get("confidence"))
    base = score if score > D0 else level_factor
    return _clamp(base * Decimal("0.7500") + confidence * Decimal("0.2500"))


def _param_support_value(param_code: str, item: Mapping[str, Any]) -> Decimal:
    confidence = _decimal(item.get("confidence"))
    numeric_value = _decimal(item.get("numeric_value"))
    value = str(item.get("value") or "").lower()
    if any(token in value for token in ("true", "yes", "支持", "有", "是")):
        return _clamp(Decimal("0.8000") * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if param_code in {"screen_size_inch"} and numeric_value > 0:
        return _clamp((Decimal("0.8500") if numeric_value >= 75 else Decimal("0.4500")) * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if param_code in {"peak_brightness_nits"} and numeric_value > 0:
        return _clamp((Decimal("0.9000") if numeric_value >= 1000 else Decimal("0.5500")) * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if param_code in {"dimming_zones"} and numeric_value > 0:
        return _clamp((Decimal("0.8500") if numeric_value >= 100 else Decimal("0.5000")) * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if param_code in {"native_refresh_rate_hz", "system_refresh_rate_hz"} and numeric_value > 0:
        return _clamp((Decimal("0.8500") if numeric_value >= 120 else Decimal("0.4500")) * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if param_code in {"hdmi_2_1_ports"} and numeric_value > 0:
        return _clamp((Decimal("0.8000") if numeric_value >= 1 else D0) * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if param_code in {"speaker_power_w"} and numeric_value > 0:
        return _clamp((Decimal("0.7500") if numeric_value >= 40 else Decimal("0.4500")) * Decimal("0.8000") + confidence * Decimal("0.2000"))
    if numeric_value > 0 or value:
        return _clamp(Decimal("0.5000") * Decimal("0.8000") + confidence * Decimal("0.2000"))
    return D0


def _price_fit_score(battlefield_code: str, price_band: str, screen_size: Decimal) -> Decimal:
    if battlefield_code == "BF_PREMIUM_PICTURE":
        return Decimal("0.8000") if price_band in {"mid_high", "high"} else Decimal("0.3500")
    if battlefield_code in {"BF_FAMILY_VIEWING_UPGRADE", "BF_GAMING_SPORTS", "BF_CINEMA_AUDIO_IMMERSION"}:
        return Decimal("0.7000") if price_band in {"mid", "mid_high", "high"} else Decimal("0.3500")
    if battlefield_code == "BF_LARGE_SCREEN_VALUE":
        if screen_size >= Decimal("75") and price_band in {"low", "mid_low", "mid"}:
            return Decimal("0.8500")
        return Decimal("0.4500") if screen_size >= Decimal("75") else Decimal("0.2500")
    if battlefield_code in {"BF_FAMILY_EYE_CARE", "BF_SENIOR_EASE_OF_USE", "BF_SMART_SYSTEM_EXPERIENCE"}:
        return Decimal("0.6000") if price_band in {"low", "mid_low", "mid", "mid_high"} else Decimal("0.4500")
    if battlefield_code in {"BF_DESIGN_HOME_FIT", "BF_SERVICE_ASSURANCE"}:
        return Decimal("0.5500") if screen_size > 0 or price_band else D0
    return Decimal("0.3000") if price_band else D0


def _battlefield_definition_meta(battlefield: Mapping[str, Any] | None) -> dict[str, Any]:
    if not battlefield:
        return {}
    return dict(battlefield.get("_m08_5_definition") or {})


def _battlefield_v2_rule_for(battlefield_code: str, battlefield: Mapping[str, Any] | None = None) -> dict[str, Any]:
    meta = _battlefield_definition_meta(battlefield)
    rule = dict(BATTLEFIELD_V2_RULES.get(battlefield_code) or {})
    v2_definition = dict(meta.get("v2_definition") or {})
    for key, value in v2_definition.items():
        if value is not None:
            rule[key] = value
    if meta:
        rule["name_cn"] = meta.get("dimension_name_cn") or rule.get("name_cn")
        rule["definition_cn"] = meta.get("definition_cn") or rule.get("definition_cn")
    return rule


def _battlefield_v2_rule(battlefield_code: str) -> dict[str, Any]:
    return _battlefield_v2_rule_for(battlefield_code)


def _battlefield_v2_payload(battlefield_code: str, battlefield: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rule = _battlefield_v2_rule_for(battlefield_code, battlefield)
    meta = _battlefield_definition_meta(battlefield)
    downstream_policy = dict(meta.get("downstream_policy_json") or {})
    return {
        "v2_code": rule.get("v2_code") or battlefield_code,
        "name_cn": rule.get("name_cn"),
        "definition_cn": rule.get("definition_cn"),
        "migration_action": rule.get("migration_action") or "legacy",
        "merged_into": rule.get("merged_into"),
        "anchor_groups": list(rule.get("anchor_groups") or ()),
        "market_pool_fit": dict(rule.get("market_pool_fit") or {}),
        "definition_source": "m08_5_active_ontology" if meta else "seed_v2_rule",
        "definition_status": meta.get("definition_status"),
        "boundary_policy": meta.get("boundary_policy"),
        "allocation_policy": meta.get("allocation_policy"),
        "allocation_block_reasons": list(downstream_policy.get("allocation_block_reasons") or ()),
        "allocation_eligible": _v2_allocation_eligible(battlefield_code, battlefield),
    }


def _v2_allocation_eligible(battlefield_code: str, battlefield: Mapping[str, Any] | None = None) -> bool:
    if battlefield_code == SERVICE_BATTLEFIELD_CODE:
        return False
    meta = _battlefield_definition_meta(battlefield)
    if meta:
        if str(meta.get("definition_status") or "") in {"disabled", "blocked"}:
            return False
        if str(meta.get("boundary_policy") or "") != "product_value":
            return False
        if str(meta.get("allocation_policy") or "") in {"never_allocate", "candidate_only", "review_required"}:
            return False
        downstream_policy = dict(meta.get("downstream_policy_json") or {})
        if downstream_policy.get("allocation_eligible") is False:
            return False
    action = str(_battlefield_v2_rule_for(battlefield_code, battlefield).get("migration_action") or "")
    return action not in V2_NON_PRODUCT_ACTIONS


def _score_allocation_eligible(score: M11SkuBattlefieldScoreRecord, battlefield: Mapping[str, Any] | None = None) -> bool:
    if not _v2_allocation_eligible(score.battlefield_code, battlefield):
        return False
    meta = _battlefield_definition_meta(battlefield)
    allocation_policy = str(meta.get("allocation_policy") or "")
    score_breakdown = dict(score.score_breakdown_json or {})
    if allocation_policy == "eligible_when_product_anchor_present":
        if _decimal(score_breakdown.get("product_anchor")) < Decimal("0.3000"):
            return False
        if _decimal(score_breakdown.get("market_pool_fit")) < Decimal("0.3000"):
            return False
    return True


def _price_position_from_percentile(percentile: Decimal) -> str:
    if percentile <= D0:
        return "unknown"
    if percentile <= Decimal("0.2000"):
        return "entry"
    if percentile <= Decimal("0.4000"):
        return "value"
    if percentile <= Decimal("0.6500"):
        return "mainstream"
    if percentile <= Decimal("0.8000"):
        return "upper_mainstream"
    if percentile <= Decimal("0.9300"):
        return "premium"
    return "flagship"


def _market_price_fit_score(
    battlefield_code: str,
    price_position: str,
    price_per_inch_percentile: Decimal,
    *,
    battlefield: Mapping[str, Any] | None = None,
) -> Decimal:
    if not price_position or price_position == "unknown":
        return D0
    allowed = set(_battlefield_v2_rule_for(battlefield_code, battlefield).get("market_pool_fit", {}).get("price_positions") or ())
    if not allowed:
        return Decimal("0.4500")
    if price_position in allowed:
        base = Decimal("0.8000")
    elif _adjacent_price_position(price_position, allowed):
        base = Decimal("0.5200")
    else:
        base = Decimal("0.2000")
    if battlefield_code == "BF_LARGE_SCREEN_VALUE" and price_per_inch_percentile > D0:
        if price_per_inch_percentile <= Decimal("0.4000"):
            base = max(base, Decimal("0.8500"))
        elif price_per_inch_percentile >= Decimal("0.8000"):
            base = min(base, Decimal("0.4500"))
    return _round4(base)


def _adjacent_price_position(price_position: str, allowed: set[str]) -> bool:
    order = ("entry", "value", "mainstream", "upper_mainstream", "premium", "flagship")
    if price_position not in order:
        return False
    index = order.index(price_position)
    return any(abs(order.index(item) - index) == 1 for item in allowed if item in order)


def _percentile_validation_score(percentile: Decimal) -> Decimal:
    if percentile <= D0:
        return D0
    if percentile >= Decimal("0.7000"):
        return Decimal("0.8500")
    if percentile >= Decimal("0.5000"):
        return Decimal("0.7000")
    if percentile >= Decimal("0.3000"):
        return Decimal("0.5200")
    return Decimal("0.3500")


def _pool_strength(sample_count: int) -> Decimal:
    if sample_count >= 10:
        return Decimal("0.8000")
    if sample_count >= 4:
        return Decimal("0.6500")
    if sample_count >= 2:
        return Decimal("0.4500")
    if sample_count == 1:
        return Decimal("0.3000")
    return D0


def _market_pool_fit_score(
    *,
    battlefield_code: str,
    screen_size_class: str,
    price_position: str,
    sample_count: int,
    battlefield: Mapping[str, Any] | None = None,
) -> Decimal:
    rule = _battlefield_v2_rule_for(battlefield_code, battlefield)
    fit = dict(rule.get("market_pool_fit") or {})
    screen_classes = set(fit.get("screen_size_classes") or ())
    price_positions = set(fit.get("price_positions") or ())
    if not fit:
        return _pool_strength(sample_count)
    screen_score = Decimal("0.8500") if screen_size_class in screen_classes else Decimal("0.2500")
    price_score = _market_price_fit_score(battlefield_code, price_position, D0, battlefield=battlefield)
    sample_score = _pool_strength(sample_count)
    return _clamp(screen_score * Decimal("0.4500") + price_score * Decimal("0.4000") + sample_score * Decimal("0.1500"))


def _product_anchor_fit_score(
    battlefield_code: str,
    business_index: Mapping[str, Any],
    *,
    battlefield: Mapping[str, Any] | None = None,
) -> tuple[Decimal, dict[str, Any]]:
    required_groups = tuple(_battlefield_v2_rule_for(battlefield_code, battlefield).get("anchor_groups") or ())
    if not required_groups:
        return D0, {"required_groups": []}
    anchor_index = dict(business_index.get("product_anchor_index") or {})
    groups = dict(anchor_index.get("anchor_groups") or {})
    matched: list[dict[str, Any]] = []
    for group_code in required_groups:
        payload = groups.get(group_code)
        if not isinstance(payload, Mapping):
            continue
        score = _decimal(payload.get("overall_score"))
        source_status = str(payload.get("source_status") or "")
        if source_status == "market_only":
            score = min(score, Decimal("0.2500"))
        elif source_status == "claim_only":
            score = min(score, Decimal("0.4200"))
        if score <= D0:
            continue
        matched.append(
            {
                "group_code": group_code,
                "overall_score": score,
                "source_status": source_status,
                "param_hit_count": len(payload.get("param_hits") or []),
                "claim_hit_count": len(payload.get("claim_hits") or []),
                "market_hit_count": len(payload.get("market_hits") or []),
            }
        )
    if not matched:
        return D0, {"required_groups": list(required_groups), "matched_groups": []}
    best_score = max(_decimal(item["overall_score"]) for item in matched)
    return _clamp(best_score), {
        "required_groups": list(required_groups),
        "matched_groups": [
            {
                **item,
                "overall_score": float(_decimal(item["overall_score"])),
            }
            for item in matched
        ],
        "source_statuses": sorted({str(item["source_status"]) for item in matched if item.get("source_status")}),
    }


def _portfolio_allocation_weights(scores: Sequence[M11SkuBattlefieldScoreRecord]) -> dict[str, Decimal]:
    weighted: list[tuple[str, Decimal]] = []
    for index, score in enumerate(scores):
        role_boost = Decimal("1.2000") if index == 0 else Decimal("1.0000")
        value = _clamp(score.battlefield_score * role_boost * (Decimal("0.7500") + _decimal(score.confidence) * Decimal("0.2500")))
        if value > D0:
            weighted.append((score.battlefield_code, value))
    total = sum(value for _, value in weighted)
    if total <= D0:
        return {}
    return {code: _q6(value / total) for code, value in weighted}


def _semantic_market_weights(battlefield: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
    weights = dict(battlefield.get("semantic_market_weights") or {})
    semantic = _decimal(weights.get("semantic"))
    market = _decimal(weights.get("market"))
    if semantic > D0 or market > D0:
        total = semantic + market
        if total > D0:
            return _round4(semantic / total), _round4(market / total)
    code = str(battlefield.get("battlefield_code") or "")
    if code == "BF_LARGE_SCREEN_VALUE":
        return Decimal("0.5500"), Decimal("0.4500")
    if code == "BF_SERVICE_ASSURANCE":
        return Decimal("0.8000"), Decimal("0.2000")
    return Decimal("0.7000"), Decimal("0.3000")


def _relation_level(
    score: Decimal,
    semantic_score: Decimal,
    market_score: Decimal,
    coverage: Mapping[str, Any],
    risk: _RiskEvaluation,
) -> M11BattlefieldRelationLevel:
    if risk.blocked_reason:
        return M11BattlefieldRelationLevel.BLOCKED
    positive_domains = set(coverage.get("positive_domains") or [])
    if (
        score >= Decimal("0.7500")
        and semantic_score >= Decimal("0.5500")
        and market_score >= Decimal("0.3500")
        and len(positive_domains) >= 3
    ):
        return M11BattlefieldRelationLevel.MAIN
    if score >= Decimal("0.6000") and len(positive_domains) >= 2:
        return M11BattlefieldRelationLevel.SECONDARY
    if score >= Decimal("0.4500"):
        return M11BattlefieldRelationLevel.OPPORTUNITY
    if score >= Decimal("0.3500"):
        return M11BattlefieldRelationLevel.WEAK
    return M11BattlefieldRelationLevel.INSUFFICIENT


def _selection_role(
    battlefield_code: str,
    relation_level: M11BattlefieldRelationLevel,
) -> M11CompetitorSelectionRole:
    if battlefield_code == "BF_SERVICE_ASSURANCE":
        return M11CompetitorSelectionRole.RISK_OR_SERVICE_CONTEXT
    if relation_level == M11BattlefieldRelationLevel.MAIN:
        return M11CompetitorSelectionRole.PRIMARY_SEARCH_CONTEXT
    if relation_level == M11BattlefieldRelationLevel.SECONDARY:
        return M11CompetitorSelectionRole.SECONDARY_SEARCH_CONTEXT
    if relation_level == M11BattlefieldRelationLevel.OPPORTUNITY:
        return M11CompetitorSelectionRole.OPPORTUNITY_MONITORING
    return M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH


def _selection_role_cn(role: M11CompetitorSelectionRole) -> str:
    return {
        M11CompetitorSelectionRole.PRIMARY_SEARCH_CONTEXT: "主召回语境",
        M11CompetitorSelectionRole.SECONDARY_SEARCH_CONTEXT: "辅助召回语境",
        M11CompetitorSelectionRole.OPPORTUNITY_MONITORING: "机会监控语境",
        M11CompetitorSelectionRole.RISK_OR_SERVICE_CONTEXT: "服务/风险语境",
        M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH: "不进入核心召回",
    }[role]


def _sample_sufficiency(market_evidence: M11BattlefieldDomainEvidence) -> M11BattlefieldSampleSufficiency:
    sample_status = str(market_evidence.risk_json.get("sample_status") or "")
    if sample_status in {"sufficient", "limited", "insufficient"}:
        return M11BattlefieldSampleSufficiency(sample_status)
    if int(market_evidence.risk_json.get("pool_count") or 0) > 0:
        return M11BattlefieldSampleSufficiency.SUFFICIENT
    return M11BattlefieldSampleSufficiency.UNKNOWN


def _candidate_status(
    relation_level: M11BattlefieldRelationLevel,
    risk: _RiskEvaluation,
    domain_evidence: Mapping[M11BattlefieldEvidenceDomain, M11BattlefieldDomainEvidence],
) -> M11BattlefieldCandidateStatus:
    if relation_level == M11BattlefieldRelationLevel.BLOCKED:
        return M11BattlefieldCandidateStatus.BLOCKED
    if relation_level == M11BattlefieldRelationLevel.INSUFFICIENT and not any(item.score > 0 for item in domain_evidence.values()):
        return M11BattlefieldCandidateStatus.REJECTED
    if risk.review_issues:
        return M11BattlefieldCandidateStatus.REVIEW_REQUIRED
    return M11BattlefieldCandidateStatus.ACTIVE


def _candidate_sources(domain_evidence: Mapping[M11BattlefieldEvidenceDomain, M11BattlefieldDomainEvidence]) -> list[str]:
    result: list[str] = []
    mapping = {
        M11BattlefieldEvidenceDomain.TASK: M11BattlefieldCandidateSource.TASK,
        M11BattlefieldEvidenceDomain.TARGET_GROUP: M11BattlefieldCandidateSource.TARGET_GROUP,
        M11BattlefieldEvidenceDomain.CLAIM: M11BattlefieldCandidateSource.CLAIM,
        M11BattlefieldEvidenceDomain.PARAM: M11BattlefieldCandidateSource.PARAM,
        M11BattlefieldEvidenceDomain.COMMENT: M11BattlefieldCandidateSource.COMMENT,
        M11BattlefieldEvidenceDomain.MARKET: M11BattlefieldCandidateSource.MARKET,
        M11BattlefieldEvidenceDomain.SERVICE: M11BattlefieldCandidateSource.SERVICE,
    }
    for domain, source in mapping.items():
        if domain_evidence[domain].score > 0:
            result.append(source.value)
    if not result:
        result.append(M11BattlefieldCandidateSource.SEED_GAP.value)
    return _dedupe(result)


def _domain_coverage_json(domain_evidence: Mapping[M11BattlefieldEvidenceDomain, M11BattlefieldDomainEvidence]) -> dict[str, Any]:
    counted_domains = {
        domain: evidence
        for domain, evidence in domain_evidence.items()
        if domain in {
            M11BattlefieldEvidenceDomain.TASK,
            M11BattlefieldEvidenceDomain.TARGET_GROUP,
            M11BattlefieldEvidenceDomain.CLAIM,
            M11BattlefieldEvidenceDomain.PARAM,
            M11BattlefieldEvidenceDomain.COMMENT,
            M11BattlefieldEvidenceDomain.MARKET,
        }
    }
    domain_scores = {domain.value: float(evidence.score) for domain, evidence in domain_evidence.items()}
    positive_domains = [domain.value for domain, evidence in counted_domains.items() if evidence.score >= Decimal("0.2500")]
    return {
        "domain_scores": domain_scores,
        "positive_domains": positive_domains,
        "positive_domain_count": len(positive_domains),
        "has_task": M11BattlefieldEvidenceDomain.TASK.value in positive_domains,
        "has_target_group": M11BattlefieldEvidenceDomain.TARGET_GROUP.value in positive_domains,
        "has_product_evidence": bool(
            {
                M11BattlefieldEvidenceDomain.CLAIM.value,
                M11BattlefieldEvidenceDomain.PARAM.value,
            }
            & set(positive_domains)
        ),
        "has_market": M11BattlefieldEvidenceDomain.MARKET.value in positive_domains,
    }


def _confidence(score: Decimal, profile_confidence: Any, coverage: Mapping[str, Any], risk: _RiskEvaluation) -> Decimal:
    domain_count = Decimal(int(coverage.get("positive_domain_count") or 0))
    domain_factor = min(domain_count / Decimal("6"), D1)
    risk_factor = Decimal("0.9000") if risk.review_issues else D1
    return _clamp((score * Decimal("0.6200") + _decimal(profile_confidence) * Decimal("0.2500") + domain_factor * Decimal("0.1300")) * risk_factor)


def _confidence_level(confidence: Decimal) -> Core3ConfidenceLevel:
    if confidence >= Decimal("0.7000"):
        return Core3ConfidenceLevel.HIGH
    if confidence >= Decimal("0.5000"):
        return Core3ConfidenceLevel.MEDIUM
    if confidence > 0:
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def _relation_reason_json(
    relation_level: M11BattlefieldRelationLevel,
    semantic_score: Decimal,
    market_score: Decimal,
    coverage: Mapping[str, Any],
    risk: _RiskEvaluation,
) -> dict[str, Any]:
    return {
        "relation_level": relation_level.value,
        "semantic_score": float(semantic_score),
        "market_score": float(market_score),
        "positive_domains": coverage.get("positive_domains") or [],
        "caps": list(risk.caps),
        "issues": list(risk.review_issues),
    }


def _missing_signals(domain_evidence: Mapping[M11BattlefieldEvidenceDomain, M11BattlefieldDomainEvidence]) -> list[dict[str, Any]]:
    return [
        {"domain": domain.value, "reason_cn": evidence.reason_cn}
        for domain, evidence in domain_evidence.items()
        if evidence.support_level == M11BattlefieldSupportLevel.MISSING
    ]


def _candidate_reason_cn(status: M11BattlefieldCandidateStatus, battlefield_name: str, business_parts: Mapping[str, str]) -> str:
    if status == M11BattlefieldCandidateStatus.BLOCKED:
        return business_parts.get("待复核点", "输入阻塞。")
    if status == M11BattlefieldCandidateStatus.REJECTED:
        return f"{battlefield_name} 的任务、客群、卖点、参数、评论和市场验证均不足，暂不作为价值战场。"
    if status == M11BattlefieldCandidateStatus.REVIEW_REQUIRED:
        return f"{battlefield_name} 已有战场线索，但存在待复核限制：{business_parts.get('待复核点', '')}"
    return f"{battlefield_name} 已进入价值战场候选，判断依据为任务、客群、卖点、参数、评论和市场验证。"


def _processing_status(status: M11BattlefieldCandidateStatus, issues: Sequence[Mapping[str, Any]]) -> str:
    if status == M11BattlefieldCandidateStatus.BLOCKED:
        return "blocked"
    if issues:
        return "warning"
    return "success"


def _support_level(score: Decimal) -> M11BattlefieldSupportLevel:
    if score >= Decimal("0.7500"):
        return M11BattlefieldSupportLevel.STRONG
    if score >= Decimal("0.5500"):
        return M11BattlefieldSupportLevel.MEDIUM
    if score > 0:
        return M11BattlefieldSupportLevel.WEAK
    return M11BattlefieldSupportLevel.MISSING


def _keyword_hit(battlefield: Mapping[str, Any], phrases: Sequence[str]) -> bool:
    tokens = [str(item).lower() for item in [*list(battlefield.get("aliases") or []), *list(battlefield.get("keywords") or [])] if item]
    corpus = " ".join(str(item).lower() for item in phrases if item)
    return bool(corpus and any(token in corpus for token in tokens))


def _issue(issue_type: M11BattlefieldReviewIssueType, reason_cn: str, *, severity: str = "warning") -> dict[str, Any]:
    return {
        "issue_type": issue_type.value,
        "reason_cn": reason_cn,
        "severity": severity,
        "suggestion_cn": "补充上游证据或业务复核后重新运行 M11。",
    }


def _plain_issue(issue_type: str, reason_cn: str, *, severity: str = "warning") -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "reason_cn": reason_cn,
        "severity": severity,
        "suggestion_cn": "复核上游参数、卖点、市场池和新版维度定义后重新运行 M11。",
    }


def _feature_view_hash(bundle: M11InputBundle) -> str:
    return bundle.feature_view.view_hash if bundle.feature_view is not None else "missing_feature_view"


def _portfolio_item(
    score: M11SkuBattlefieldScoreRecord,
    *,
    relation_level: str | None = None,
    allocation_role: str | None = None,
    allocation_weight: Decimal = D0,
    allocation_eligible: bool = False,
) -> dict[str, Any]:
    score_breakdown = dict(score.score_breakdown_json or {})
    next_payload = dict(score.next_module_payload_json or {})
    v2_payload = dict(next_payload.get("battlefield_v2") or _battlefield_v2_payload(score.battlefield_code))
    return {
        "sku_battlefield_score_id": score.sku_battlefield_score_id,
        "battlefield_code": score.battlefield_code,
        "battlefield_name_cn": score.battlefield_name_cn,
        "battlefield_score": float(score.battlefield_score),
        "relation_level": relation_level or _enum_value(score.relation_level),
        "score_record_relation_level": _enum_value(score.relation_level),
        "competitor_selection_role": score.competitor_selection_role,
        "confidence": float(score.confidence),
        "business_reason_cn": score.business_reason_cn,
        "allocation_role": allocation_role or "not_allocated",
        "allocation_weight": float(_q6(allocation_weight)),
        "allocation_eligible": allocation_eligible,
        "battlefield_v2": v2_payload,
        "market_pool_key": score_breakdown.get("market_pool_key"),
        "screen_size_class": score_breakdown.get("screen_size_class"),
        "price_position": score_breakdown.get("price_position"),
        "product_anchor_score": score_breakdown.get("product_anchor"),
        "product_anchor_groups": score_breakdown.get("product_anchor_groups") or [],
    }


def _record_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash([str(item) for item in parts], version=f'{prefix}_id_v1')[:24]}"


def _decimal(value: Any) -> Decimal:
    if value is None:
        return D0
    return Decimal(str(value))


def _average(values: Sequence[Any]) -> Decimal:
    decimals = [_decimal(value) for value in values if _decimal(value) > D0]
    if not decimals:
        return D0
    return _round4(sum(decimals) / Decimal(len(decimals)))


def _clamp(value: Decimal) -> Decimal:
    return max(D0, min(D1, _round4(value)))


def _round4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _q6(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


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
        if key in CORE3_M11_FORBIDDEN_OUTPUT_FIELDS:
            raise ValueError(f"M11 输出越界字段：{key}")
        if isinstance(value, Mapping):
            _assert_no_forbidden_fields(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    _assert_no_forbidden_fields(item)
