"""SOP orchestrators for CatForge analyst.

SOPs stay as thin compositions over atomic analyst abilities. They do not
query tables directly; atomic handlers remain the source of fact extraction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext, AnalystStatus, base_result
from app.services.core3_real_data.analyst.atomic_handlers import AtomicAnalystHandlers
from app.services.core3_real_data.analyst.competitor_answer import build_competitor_answer
from app.services.core3_real_data.analyst.low_sales_answer import build_low_sales_answer


CLAIM_VALUE_REPORT_LIMIT = 200
LOW_SALES_RATIO_THRESHOLD = Decimal("0.75")
LOW_AMOUNT_RATIO_THRESHOLD = Decimal("0.90")
NOT_WEAK_SALES_RATIO_THRESHOLD = Decimal("0.90")
NOT_WEAK_AMOUNT_RATIO_THRESHOLD = Decimal("1.00")
MIN_OVERLAP_WEEKS = 4


SOP_STEP_MAP: dict[str, tuple[str, ...]] = {
    "competitor-set": (
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
        "semantic-overlap",
        "param-claim-overlap",
        "sales-overlap",
    ),
    "why-sales-diff": (
        "resolve-sku",
        "sales-overlap",
        "semantic-overlap",
        "param-claim-overlap",
        "comment-support",
    ),
    "premium-claim-drivers": (
        "sku-fact-brief",
        "sku-claim-value",
        "claim-contribution",
        "claim-opportunity-gaps",
        "comment-support",
        "opportunity-gaps",
        "semantic-dimension-space",
    ),
    "battlefield-space": ("semantic-dimension-space",),
    "battlefield-opportunity": (
        "sku-fact-brief",
        "opportunity-gaps",
        "semantic-dimension-space",
    ),
    "low-sales-diagnosis": (
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
        "competitor-set",
        "why-sales-diff",
        "claim-value-compare",
        "premium-claim-drivers",
        "claim-opportunity-gaps",
        "battlefield-opportunity",
    ),
    "sku-business-brief": (
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
        "opportunity-gaps",
        "semantic-dimension-space",
    ),
}


class SopOrchestrators:
    def __init__(self, atomic_handlers: AtomicAnalystHandlers) -> None:
        self.atomic_handlers = atomic_handlers

    def dispatch(self, command: str, context: AnalystContext, **kwargs: Any) -> dict[str, Any]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "competitor-set": self.competitor_set,
            "sku-business-brief": self.sku_business_brief,
            "why-sales-diff": self.why_sales_diff,
            "premium-claim-drivers": self.premium_claim_drivers,
            "battlefield-space": self.battlefield_space,
            "battlefield-opportunity": self.battlefield_opportunity,
            "low-sales-diagnosis": self.low_sales_diagnosis,
        }
        handler = handlers.get(command)
        if handler is None:
            return self.planned_sop(context, command=command, **kwargs)
        return handler(context, **kwargs)

    def competitor_set(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
        answer_style: str = "raw",
        with_report: str = "none",
        top_n: int = 3,
        max_chat_chars: int = 600,
        report_title: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        target = self.atomic_handlers.resolve_sku(context, query=query, sku_code=sku_code, model_name=model_name, limit=10)
        if not _ok(target):
            return _sop_error(command="competitor-set", context=context, atom_results=[target], message_cn="竞品集合生成前未能唯一解析目标 SKU。")
        target_sku = target["target"]["sku_code"]
        fact = self.atomic_handlers.sku_fact_brief(context, sku_code=target_sku, limit=limit)
        candidates_result = self.atomic_handlers.same_size_price_candidates(context, sku_code=target_sku, limit=limit)
        candidate_rows = (((candidates_result.get("result") or {}).get("candidate_search") or {}).get("candidates") or [])[:limit]
        competitors: list[dict[str, Any]] = []
        pair_atom_results: list[dict[str, Any]] = []
        need_candidate_fact = answer_style == "xiaoao" or with_report != "none"
        claim_value_limit = max(limit, CLAIM_VALUE_REPORT_LIMIT)
        target_claim_value = self.atomic_handlers.sku_claim_value(context, sku_code=target_sku, limit=claim_value_limit) if need_candidate_fact else {}
        target_claim_contribution = self.atomic_handlers.claim_contribution(context, sku_code=target_sku, limit=claim_value_limit) if need_candidate_fact else {}
        for rank, row in enumerate(candidate_rows, start=1):
            candidate_sku = row.get("sku_code")
            if not candidate_sku:
                continue
            semantic = self.atomic_handlers.semantic_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku)
            param_claim = self.atomic_handlers.param_claim_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku)
            sales = self.atomic_handlers.sales_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku)
            candidate_fact = self.atomic_handlers.sku_fact_brief(context, sku_code=candidate_sku, limit=limit) if need_candidate_fact else {}
            candidate_claim_value = self.atomic_handlers.sku_claim_value(context, sku_code=candidate_sku, limit=claim_value_limit) if need_candidate_fact else {}
            candidate_claim_contribution = self.atomic_handlers.claim_contribution(context, sku_code=candidate_sku, limit=claim_value_limit) if need_candidate_fact else {}
            pair_atom_results.extend([semantic, param_claim, sales])
            if candidate_fact:
                pair_atom_results.append(candidate_fact)
            if candidate_claim_value:
                pair_atom_results.append(candidate_claim_value)
            if candidate_claim_contribution:
                pair_atom_results.append(candidate_claim_contribution)
            competitors.append(
                _competitor_item(
                    rank,
                    row,
                    semantic,
                    param_claim,
                    sales,
                    candidate_fact,
                    candidate_claim_value,
                    candidate_claim_contribution,
                )
            )
        target_claim_atoms = [atom for atom in (target_claim_value, target_claim_contribution) if atom]
        atom_results = [target, fact, candidates_result, *target_claim_atoms, *pair_atom_results]
        target_fact_brief = (fact.get("result") or {}).get("fact_brief", {})
        result_payload: dict[str, Any] = {
            "competitor_set": {
                "ranking_policy": [
                    "same_size_price_pool",
                    "same_value_battlefield",
                    "same_user_task_or_target_group",
                    "param_claim_overlap",
                    "sales_overlap_validation",
                ],
                "target_fact_brief": target_fact_brief,
                "target_claim_value": ((target_claim_value or {}).get("result") or {}).get("sku_claim_value", {}),
                "target_claim_contribution": ((target_claim_contribution or {}).get("result") or {}).get("claim_contribution", {}),
                "candidate_count": len(competitors),
                "candidates": competitors,
            }
        }
        if answer_style == "xiaoao" or with_report != "none":
            result_payload["competitor_answer"] = build_competitor_answer(
                target=target["target"],
                target_fact_brief=target_fact_brief,
                target_claim_value=target_claim_value,
                target_claim_contribution=target_claim_contribution,
                competitors=competitors,
                top_n=top_n,
                max_chat_chars=max_chat_chars,
                with_report=with_report,
                report_title=report_title,
            )
        return base_result(
            status=AnalystStatus.OK,
            command="competitor-set",
            context=context,
            target=target["target"],
            result=result_payload,
            sop_steps=_steps("competitor-set", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=[f"已按购买池、主辅语义重合、价值锚点替代压力和市场验证生成 {len(competitors)} 个竞品候选。"],
        )

    def sku_business_brief(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
        **_: Any,
    ) -> dict[str, Any]:
        target = self.atomic_handlers.resolve_sku(context, query=query, sku_code=sku_code, model_name=model_name, limit=10)
        if not _ok(target):
            return _sop_error(command="sku-business-brief", context=context, atom_results=[target], message_cn="业务画像生成前未能唯一解析目标 SKU。")
        target_sku = target["target"]["sku_code"]
        fact = self.atomic_handlers.sku_fact_brief(context, sku_code=target_sku, limit=limit)
        candidates = self.atomic_handlers.same_size_price_candidates(context, sku_code=target_sku, limit=min(limit, 5))
        gaps = self.atomic_handlers.opportunity_gaps(context, sku_code=target_sku, limit=limit)
        primary_battlefield_code = _primary_battlefield_code(fact)
        primary_space = (
            self.atomic_handlers.semantic_dimension_space(context, dimension_type="battlefield", dimension_code=primary_battlefield_code, limit=limit)
            if primary_battlefield_code
            else {}
        )
        fact_brief = (fact.get("result") or {}).get("fact_brief", {})
        sections = fact_brief.get("sections") or {}
        market = sections.get("market") or {}
        user_task = sections.get("user_task") or {}
        target_group = sections.get("target_group") or {}
        battlefield = sections.get("value_battlefield") or {}
        atom_results = [target, fact, candidates, gaps, primary_space]
        return base_result(
            status=AnalystStatus.OK,
            command="sku-business-brief",
            context=context,
            target=target["target"],
            result={
                "sku_business_brief": {
                    "identity": target["target"],
                    "market_position": market.get("market_position") or {},
                    "market_metrics": market.get("market_metrics") or {},
                    "primary_semantics": {
                        "primary_user_task_code": user_task.get("primary_user_task_code"),
                        "primary_target_group_code": target_group.get("primary_target_group_code"),
                        "primary_battlefield_code": battlefield.get("primary_battlefield_code"),
                    },
                    "fact_brief": fact_brief,
                    "top_same_size_price_candidates": (((candidates.get("result") or {}).get("candidate_search") or {}).get("candidates") or [])[:5],
                    "opportunity_and_risk": {
                        "opportunity_battlefields": ((gaps.get("result") or {}).get("opportunity_gaps") or {}).get("opportunity_battlefields", []),
                        "drag_factor_battlefields": ((gaps.get("result") or {}).get("opportunity_gaps") or {}).get("drag_factor_battlefields", []),
                        "price_gap_signals": ((gaps.get("result") or {}).get("opportunity_gaps") or {}).get("price_gap_signals", []),
                        "claim_gap_signals": ((gaps.get("result") or {}).get("opportunity_gaps") or {}).get("claim_gap_signals", []),
                    },
                    "primary_battlefield_space": (primary_space.get("result") or {}) if primary_space else {},
                }
            },
            sop_steps=_steps("sku-business-brief", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=["已生成单 SKU 的市场位置、事实画像、主要语义归属、同池竞品和机会风险摘要。"],
        )

    def why_sales_diff(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        candidate_sku_code: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        if not candidate_sku_code:
            return base_result(
                status=AnalystStatus.ERROR,
                command="why-sales-diff",
                context=context,
                limitations=["why-sales-diff 需要 candidate_sku_code。"],
                message_cn="请提供对比 SKU code。",
            )
        sales = self.atomic_handlers.sales_overlap(context, query=query, sku_code=sku_code, model_name=model_name, candidate_sku_code=candidate_sku_code)
        if not _ok(sales):
            return _sop_error(command="why-sales-diff", context=context, atom_results=[sales], message_cn="销量差异分析前未能解析目标或对比 SKU。")
        target_sku = sales["target"]["sku_code"]
        semantic = self.atomic_handlers.semantic_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku_code)
        param_claim = self.atomic_handlers.param_claim_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku_code)
        target_comment = self.atomic_handlers.comment_support(context, sku_code=target_sku)
        candidate_comment = self.atomic_handlers.comment_support(context, sku_code=candidate_sku_code)
        atom_results = [sales, semantic, param_claim, target_comment, candidate_comment]
        return base_result(
            status=AnalystStatus.OK,
            command="why-sales-diff",
            context=context,
            target=sales["target"],
            result={
                "why_sales_diff": {
                    "candidate": (sales.get("result") or {}).get("candidate", {}),
                    "sales_overlap": (sales.get("result") or {}).get("sales_overlap", {}),
                    "semantic_overlap": (semantic.get("result") or {}).get("semantic_overlap", {}),
                    "param_claim_overlap": (param_claim.get("result") or {}).get("param_claim_overlap", {}),
                    "comment_support": {
                        "target": ((target_comment.get("result") or {}).get("comment_support") or {}),
                        "candidate": ((candidate_comment.get("result") or {}).get("comment_support") or {}),
                    },
                    "factor_summary": _sales_diff_factor_summary(sales, semantic, param_claim, target_comment, candidate_comment),
                }
            },
            sop_steps=_steps("why-sales-diff", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=["已基于重叠在售周销量、语义重合、参数卖点重合和评论支撑生成销量差异分析材料。"],
        )

    def premium_claim_drivers(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
        **_: Any,
    ) -> dict[str, Any]:
        fact = self.atomic_handlers.sku_fact_brief(context, query=query, sku_code=sku_code, model_name=model_name, limit=limit)
        if not _ok(fact):
            return _sop_error(command="premium-claim-drivers", context=context, atom_results=[fact], message_cn="溢价卖点分析前未能唯一解析目标 SKU。")
        target_sku = fact["target"]["sku_code"]
        claim_value = self.atomic_handlers.sku_claim_value(context, sku_code=target_sku, limit=limit)
        contribution = self.atomic_handlers.claim_contribution(context, sku_code=target_sku, limit=limit)
        claim_gaps = self.atomic_handlers.claim_opportunity_gaps(context, sku_code=target_sku, limit=limit)
        comment = self.atomic_handlers.comment_support(context, sku_code=target_sku)
        gaps = self.atomic_handlers.opportunity_gaps(context, sku_code=target_sku, limit=limit)
        primary_battlefield_code = _primary_battlefield_code(fact)
        primary_space = (
            self.atomic_handlers.semantic_dimension_space(context, dimension_type="battlefield", dimension_code=primary_battlefield_code, limit=limit)
            if primary_battlefield_code
            else {}
        )
        atom_results = [fact, claim_value, contribution, claim_gaps, comment, gaps, primary_space]
        return base_result(
            status=AnalystStatus.OK,
            command="premium-claim-drivers",
            context=context,
            target=fact["target"],
            result={
                "premium_claim_drivers": _premium_claim_driver_payload(fact, comment, gaps, primary_space, claim_value, contribution, claim_gaps),
            },
            sop_steps=_steps("premium-claim-drivers", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=["已按 M12C 用户卖点支付价值、事实卖点、评论支撑、主/辅战场和价格压力信号识别高溢价、份额转化、客户获得价值、门槛、待激活、竞品拦截和价格压力卖点。"],
        )

    def battlefield_space(
        self,
        context: AnalystContext,
        *,
        dimension_type: str | None = None,
        dimension_code: str | None = None,
        query: str | None = None,
        brand_name: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        limit: int = 20,
        **_: Any,
    ) -> dict[str, Any]:
        space = self.atomic_handlers.semantic_dimension_space(
            context,
            dimension_type=dimension_type or "battlefield",
            dimension_code=dimension_code,
            query=query,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band=price_band,
            limit=limit,
        )
        if not _ok(space):
            return _sop_error(command="battlefield-space", context=context, atom_results=[space], message_cn="未找到匹配的价值战场空间。")
        return base_result(
            status=AnalystStatus.OK,
            command="battlefield-space",
            context=context,
            result={"battlefield_space": (space.get("result") or {})},
            sop_steps=_steps("battlefield-space", [space]),
            atoms_used=_atoms_used([space]),
            evidence=_evidence([space]),
            limitations=_limitations([space]),
            answer_outline=["已返回价值战场图谱、市场空间、SKU 贡献和分布。"],
        )

    def battlefield_opportunity(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
        **_: Any,
    ) -> dict[str, Any]:
        fact = self.atomic_handlers.sku_fact_brief(context, query=query, sku_code=sku_code, model_name=model_name, limit=limit)
        if not _ok(fact):
            return _sop_error(command="battlefield-opportunity", context=context, atom_results=[fact], message_cn="战场机会分析前未能唯一解析目标 SKU。")
        target_sku = fact["target"]["sku_code"]
        gaps = self.atomic_handlers.opportunity_gaps(context, sku_code=target_sku, limit=limit)
        opportunity_codes = [
            item.get("dimension_code")
            for item in (((gaps.get("result") or {}).get("opportunity_gaps") or {}).get("opportunity_battlefields") or [])
            if item.get("dimension_code")
        ]
        drag_codes = [
            item.get("dimension_code")
            for item in (((gaps.get("result") or {}).get("opportunity_gaps") or {}).get("drag_factor_battlefields") or [])
            if item.get("dimension_code")
        ]
        spaces = [
            self.atomic_handlers.semantic_dimension_space(context, dimension_type="battlefield", dimension_code=code, limit=limit)
            for code in [*opportunity_codes, *drag_codes]
        ]
        atom_results = [fact, gaps, *spaces]
        return base_result(
            status=AnalystStatus.OK,
            command="battlefield-opportunity",
            context=context,
            target=fact["target"],
            result={
                "battlefield_opportunity": {
                    "fact_brief": (fact.get("result") or {}).get("fact_brief", {}),
                    "opportunity_gaps": (gaps.get("result") or {}).get("opportunity_gaps", {}),
                    "related_battlefield_spaces": [(space.get("result") or {}) for space in spaces if _ok(space)],
                }
            },
            sop_steps=_steps("battlefield-opportunity", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=["已汇总目标 SKU 的机会战场、拖后腿战场、缺口信号和相关战场市场空间。"],
        )

    def low_sales_diagnosis(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
        top_n: int = 3,
        answer_style: str = "raw",
        with_report: str = "none",
        max_chat_chars: int = 800,
        report_title: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        target = self.atomic_handlers.resolve_sku(context, query=query, sku_code=sku_code, model_name=model_name, limit=10)
        if not _ok(target):
            return _sop_error(command="low-sales-diagnosis", context=context, atom_results=[target], message_cn="低销量诊断前未能唯一解析目标 SKU。")
        target_sku = target["target"]["sku_code"]
        fact = self.atomic_handlers.sku_fact_brief(context, sku_code=target_sku, limit=limit)
        candidates = self.atomic_handlers.same_size_price_candidates(context, sku_code=target_sku, limit=limit)
        competitor_set = self.competitor_set(context, sku_code=target_sku, limit=limit, answer_style="raw")
        competitor_rows = (((competitor_set.get("result") or {}).get("competitor_set") or {}).get("candidates") or [])[: max(top_n, 0)]
        pairwise_results = [
            self.why_sales_diff(context, sku_code=target_sku, candidate_sku_code=str((row.get("candidate") or {}).get("sku_code") or ""))
            for row in competitor_rows
            if (row.get("candidate") or {}).get("sku_code")
        ]
        claim_compare_results = [
            _safe_optional_atom(
                command="claim-value-compare",
                context=context,
                call=lambda candidate_sku=candidate_sku: self.atomic_handlers.claim_value_compare(
                    context,
                    sku_code=target_sku,
                    candidate_sku_code=candidate_sku,
                    limit=limit,
                ),
                limitation_cn="竞品卖点价值对比暂不可用，低销量诊断已跳过具体竞品卖点差异。",
            )
            for candidate_sku in [str((row.get("candidate") or {}).get("sku_code") or "") for row in competitor_rows]
            if candidate_sku
        ]
        premium = _safe_optional_atom(
            command="premium-claim-drivers",
            context=context,
            call=lambda: self.premium_claim_drivers(context, sku_code=target_sku, limit=max(limit, CLAIM_VALUE_REPORT_LIMIT)),
            limitation_cn="卖点支付价值证据暂不可用，低销量诊断已先基于销量、价格和竞品证据降级输出。",
        )
        claim_gaps = _safe_optional_atom(
            command="claim-opportunity-gaps",
            context=context,
            call=lambda: self.atomic_handlers.claim_opportunity_gaps(context, sku_code=target_sku, limit=limit),
            limitation_cn="卖点机会缺口证据暂不可用，低销量诊断已跳过卖点缺口分解。",
        )
        battlefield = _safe_optional_atom(
            command="battlefield-opportunity",
            context=context,
            call=lambda: self.battlefield_opportunity(context, sku_code=target_sku, limit=limit),
            limitation_cn="战场机会证据暂不可用，低销量诊断已跳过战场客群分解。",
        )
        diagnosis_payload = _build_low_sales_diagnosis_payload(
            target=target["target"],
            fact=fact,
            candidates=candidates,
            competitor_set=competitor_set,
            pairwise_results=pairwise_results,
            claim_compare_results=claim_compare_results,
            premium=premium,
            claim_gaps=claim_gaps,
            battlefield=battlefield,
        )
        result_payload: dict[str, Any] = {"low_sales_diagnosis": diagnosis_payload}
        if answer_style == "xiaoao" or with_report != "none":
            result_payload["low_sales_answer"] = build_low_sales_answer(
                target=target["target"],
                payload=diagnosis_payload,
                with_report=with_report if with_report in {"none", "markdown", "feishu-doc"} else "none",
                max_chat_chars=max_chat_chars,
                report_title=report_title,
            )
        atom_results = [target, fact, candidates, competitor_set, *pairwise_results, *claim_compare_results, premium, claim_gaps, battlefield]
        return base_result(
            status=AnalystStatus.OK,
            command="low-sales-diagnosis",
            context=context,
            target=target["target"],
            result=result_payload,
            sop_steps=_steps("low-sales-diagnosis", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=["已按可比销量、价值棒拆解、卖点价值、竞品拦截、战场客群和评论风险生成单品低销量诊断。"],
        )

    def planned_sop(self, context: AnalystContext, *, command: str, **_: Any) -> dict[str, Any]:
        steps = [
            {"step_code": step, "status": "planned", "description_cn": "后续实现时由 catforge_analyst 原子能力执行。"}
            for step in SOP_STEP_MAP.get(command, ())
        ]
        return base_result(
            status=AnalystStatus.NOT_IMPLEMENTED,
            command=command,
            context=context,
            sop_steps=steps,
            atoms_used=[{"ability_code": step["step_code"], "status": "planned"} for step in steps],
            limitations=["该 SOP 编排入口已创建，具体原子能力编排将在后续步骤实现。"],
            message_cn=f"{command} SOP 编排尚未实现。",
        )


def _ok(result: dict[str, Any]) -> bool:
    return result.get("status") == AnalystStatus.OK.value


def _sop_error(
    *,
    command: str,
    context: AnalystContext,
    atom_results: list[dict[str, Any]],
    message_cn: str,
) -> dict[str, Any]:
    status_value = atom_results[0].get("status") if atom_results else AnalystStatus.ERROR.value
    status = AnalystStatus(status_value) if status_value in {item.value for item in AnalystStatus} else AnalystStatus.ERROR
    return base_result(
        status=status,
        command=command,
        context=context,
        result={"atom_results": atom_results},
        sop_steps=_steps(command, atom_results),
        atoms_used=_atoms_used(atom_results),
        evidence=_evidence(atom_results),
        limitations=_limitations(atom_results),
        message_cn=message_cn,
    )


def _safe_optional_atom(
    *,
    command: str,
    context: AnalystContext,
    call: Callable[[], dict[str, Any]],
    limitation_cn: str,
) -> dict[str, Any]:
    try:
        return call()
    except Exception:
        return base_result(
            status=AnalystStatus.UNSUPPORTED,
            command=command,
            context=context,
            limitations=[limitation_cn],
            message_cn=limitation_cn,
        )


def _steps(command: str, atom_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_command: dict[str, list[dict[str, Any]]] = {}
    for result in atom_results:
        by_command.setdefault(str(result.get("command")), []).append(result)
    steps: list[dict[str, Any]] = []
    for step_code in SOP_STEP_MAP.get(command, ()):
        results = by_command.get(step_code) or []
        if not results:
            status = "skipped"
        elif all(_ok(result) for result in results):
            status = "ok"
        elif any(result.get("status") == AnalystStatus.ERROR.value for result in results):
            status = "error"
        else:
            status = str(results[-1].get("status"))
        steps.append({"step_code": step_code, "status": status, "run_count": len(results)})
    return steps


def _atoms_used(atom_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for result in atom_results:
        command = result.get("command")
        if command:
            atoms.append({"ability_code": command, "status": result.get("status")})
    return atoms


def _evidence(atom_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in atom_results:
        for item in result.get("evidence") or []:
            key = (str(item.get("source_module")), str(item.get("sku_code") or item.get("row_count") or item.get("evidence_id_count") or len(evidence)))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(item)
    return evidence


def _limitations(atom_results: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for atom in atom_results:
        for item in atom.get("limitations") or []:
            if item not in result:
                result.append(item)
    return result


def _competitor_item(
    rank: int,
    candidate: dict[str, Any],
    semantic: dict[str, Any],
    param_claim: dict[str, Any],
    sales: dict[str, Any],
    candidate_fact: dict[str, Any] | None = None,
    candidate_claim_value: dict[str, Any] | None = None,
    candidate_claim_contribution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_payload = (semantic.get("result") or {}).get("semantic_overlap") or {}
    param_payload = (param_claim.get("result") or {}).get("param_claim_overlap") or {}
    sales_payload = (sales.get("result") or {}).get("sales_overlap") or {}
    semantic_score = _decimal(semantic_payload.get("semantic_overlap_score")) or Decimal("0")
    param_score = _decimal(param_payload.get("param_claim_overlap_score")) or Decimal("0")
    sales_closeness = _sales_closeness(sales_payload)
    score = Decimal("0.55") + semantic_score * Decimal("0.25") + param_score * Decimal("0.15") + sales_closeness * Decimal("0.05")
    return {
        "rank": rank,
        "candidate": candidate,
        "competitor_score": float(score),
        "basis": {
            "same_size_price_pool": True,
            "semantic_overlap_score": semantic_payload.get("semantic_overlap_score"),
            "param_claim_overlap_score": param_payload.get("param_claim_overlap_score"),
            "sales_closeness_score": float(sales_closeness),
        },
        "semantic_overlap": semantic_payload.get("overlap") or {},
        "param_claim_overlap": {
            "parameter_overlap": param_payload.get("parameter_overlap") or {},
            "claim_overlap": param_payload.get("claim_overlap") or {},
            "claim_position_overlap": param_payload.get("claim_position_overlap") or {},
        },
        "sales_overlap": sales_payload,
        "candidate_fact_brief": ((candidate_fact or {}).get("result") or {}).get("fact_brief", {}),
        "candidate_claim_value": ((candidate_claim_value or {}).get("result") or {}).get("sku_claim_value", {}),
        "candidate_claim_contribution": ((candidate_claim_contribution or {}).get("result") or {}).get("claim_contribution", {}),
    }


def _sales_closeness(sales_payload: dict[str, Any]) -> Decimal:
    comparison = sales_payload.get("comparison") or {}
    ratio = _decimal(comparison.get("target_vs_candidate_avg_weekly_volume_ratio"))
    if ratio is None or ratio <= 0:
        return Decimal("0")
    if ratio > 1:
        ratio = Decimal("1") / ratio
    return max(Decimal("0"), min(Decimal("1"), ratio))


def _sales_diff_factor_summary(
    sales: dict[str, Any],
    semantic: dict[str, Any],
    param_claim: dict[str, Any],
    target_comment: dict[str, Any],
    candidate_comment: dict[str, Any],
) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    sales_payload = (sales.get("result") or {}).get("sales_overlap") or {}
    comparison = sales_payload.get("comparison") or {}
    volume_gap = _decimal(comparison.get("target_vs_candidate_avg_weekly_volume_gap"))
    if volume_gap is not None:
        factors.append(
            {
                "factor_code": "overlap_week_sales_gap",
                "direction": "target_leads" if volume_gap > 0 else "candidate_leads" if volume_gap < 0 else "flat",
                "message_cn": "销量差异以重叠在售周周均销量为准。",
                "value": float(volume_gap),
            }
        )
    semantic_score = ((semantic.get("result") or {}).get("semantic_overlap") or {}).get("semantic_overlap_score")
    factors.append({"factor_code": "semantic_overlap", "message_cn": "语义重合用于判断是否真正在同一任务、客群和战场竞争。", "value": semantic_score})
    param_score = ((param_claim.get("result") or {}).get("param_claim_overlap") or {}).get("param_claim_overlap_score")
    factors.append({"factor_code": "param_claim_overlap", "message_cn": "参数和卖点重合用于判断产品力与表达差异。", "value": param_score})
    target_summary = (((target_comment.get("result") or {}).get("comment_support") or {}).get("available_summary") or {})
    candidate_summary = (((candidate_comment.get("result") or {}).get("comment_support") or {}).get("available_summary") or {})
    factors.append(
        {
            "factor_code": "comment_support_difference",
            "message_cn": "评论支撑差异用于判断用户是否认可对应参数和卖点。",
            "target_supported_claim_codes": target_summary.get("supported_claim_codes") or [],
            "candidate_supported_claim_codes": candidate_summary.get("supported_claim_codes") or [],
            "target_contradicted_claim_codes": target_summary.get("contradicted_claim_codes") or [],
            "candidate_contradicted_claim_codes": candidate_summary.get("contradicted_claim_codes") or [],
        }
    )
    return factors


def _primary_battlefield_code(fact: dict[str, Any]) -> str | None:
    fact_brief = (fact.get("result") or {}).get("fact_brief") or {}
    sections = fact_brief.get("sections") or {}
    battlefield = sections.get("value_battlefield") or {}
    code = battlefield.get("primary_battlefield_code")
    return str(code) if code else None


def _premium_claim_driver_payload(
    fact: dict[str, Any],
    comment: dict[str, Any],
    gaps: dict[str, Any],
    primary_space: dict[str, Any],
    claim_value: dict[str, Any] | None = None,
    contribution: dict[str, Any] | None = None,
    claim_gaps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fact_brief = (fact.get("result") or {}).get("fact_brief") or {}
    sections = fact_brief.get("sections") or {}
    claim_fact = sections.get("claim_fact") or {}
    battlefield = sections.get("value_battlefield") or {}
    user_task = sections.get("user_task") or {}
    target_group = sections.get("target_group") or {}
    comment_support = (comment.get("result") or {}).get("comment_support") or {}
    available = comment_support.get("available_summary") or {}
    fact_claim_codes = set(claim_fact.get("fact_claim_codes") or [])
    supported_claim_codes = set(available.get("supported_claim_codes") or [])
    contradicted_claim_codes = set(available.get("contradicted_claim_codes") or [])
    unsupported_claim_codes = set(claim_fact.get("unsupported_claim_codes") or [])
    claim_value_payload = ((claim_value or {}).get("result") or {}).get("sku_claim_value") or {}
    contribution_payload = ((contribution or {}).get("result") or {}).get("claim_contribution") or {}
    claim_gap_payload = ((claim_gaps or {}).get("result") or {}).get("claim_opportunity_gaps") or {}
    return {
        "premium_driver_claim_codes": sorted((fact_claim_codes & supported_claim_codes) - contradicted_claim_codes),
        "basic_support_claim_codes": sorted(fact_claim_codes - supported_claim_codes - contradicted_claim_codes),
        "brand_claim_only_codes": sorted(unsupported_claim_codes),
        "drag_factor_claim_codes": sorted(contradicted_claim_codes),
        "m12c_quantified_claim_values": claim_value_payload,
        "m12c_claim_contribution": contribution_payload,
        "m12c_claim_opportunity_gaps": claim_gap_payload,
        "semantic_context": {
            "primary_battlefield_code": battlefield.get("primary_battlefield_code"),
            "secondary_battlefield_codes": battlefield.get("secondary_battlefield_codes") or [],
            "opportunity_battlefield_codes": battlefield.get("opportunity_battlefield_codes") or [],
            "drag_factor_battlefield_codes": battlefield.get("drag_factor_battlefield_codes") or [],
            "primary_user_task_code": user_task.get("primary_user_task_code"),
            "primary_target_group_code": target_group.get("primary_target_group_code"),
        },
        "claim_fact": claim_fact,
        "comment_support": comment_support,
        "opportunity_gaps": (gaps.get("result") or {}).get("opportunity_gaps") or {},
        "primary_battlefield_space": (primary_space.get("result") or {}) if primary_space else {},
        "method_note_cn": "优先采用 M12C 在同尺寸价格带与市场场景中的可观测卖点价值量化；如 M12C 未生成，则保留事实卖点、评论支撑和主/辅战场交叉结果作为候选判断。",
    }


def _build_low_sales_diagnosis_payload(
    *,
    target: dict[str, Any],
    fact: dict[str, Any],
    candidates: dict[str, Any],
    competitor_set: dict[str, Any],
    pairwise_results: list[dict[str, Any]],
    claim_compare_results: list[dict[str, Any]],
    premium: dict[str, Any],
    claim_gaps: dict[str, Any],
    battlefield: dict[str, Any],
) -> dict[str, Any]:
    pairwise_rows = _low_sales_pairwise_rows(pairwise_results)
    sales_status = _low_sales_status(pairwise_rows)
    target_summary = _low_sales_target_summary(target, fact)
    premium_payload = ((premium.get("result") or {}).get("premium_claim_drivers") or {})
    claim_gap_payload = ((claim_gaps.get("result") or {}).get("claim_opportunity_gaps") or {})
    battlefield_payload = ((battlefield.get("result") or {}).get("battlefield_opportunity") or {})
    opportunity_gaps = battlefield_payload.get("opportunity_gaps") or {}
    claim_value_summary = _low_sales_claim_value_summary(premium_payload, claim_gap_payload)
    battlefield_summary = _low_sales_battlefield_summary(battlefield_payload)
    gap_signal_summary = _low_sales_gap_signal_summary(opportunity_gaps)
    product_line_cannibalization = _low_sales_product_line_cannibalization(
        candidates=candidates,
        target_summary=target_summary,
        claim_value_summary=claim_value_summary,
    )
    claim_compare_by_sku = _low_sales_claim_compare_by_sku(claim_compare_results)
    competitor_evidence = _low_sales_competitor_evidence(competitor_set, pairwise_rows, claim_gap_payload, claim_compare_by_sku)
    reasons = _low_sales_reason_ranking(
        target_summary=target_summary,
        sales_status=sales_status,
        claim_value_summary=claim_value_summary,
        battlefield_summary=battlefield_summary,
        gap_signal_summary=gap_signal_summary,
        competitor_evidence=competitor_evidence,
        product_line_cannibalization=product_line_cannibalization,
    )
    action_plan = _low_sales_action_plan(reasons)
    return {
        "diagnosis_version": "low_sales_diagnosis_v0.1",
        "target_summary": target_summary,
        "sales_status": sales_status,
        "value_stick_summary": _low_sales_value_stick_summary(
            sales_status=sales_status,
            reasons=reasons,
            claim_value_summary=claim_value_summary,
            competitor_evidence=competitor_evidence,
            product_line_cannibalization=product_line_cannibalization,
        ),
        "reason_ranking": reasons,
        "competitor_evidence": competitor_evidence,
        "claim_compare_summary": _low_sales_claim_compare_summary(competitor_evidence),
        "claim_value_summary": claim_value_summary,
        "battlefield_gap_summary": battlefield_summary,
        "gap_signal_summary": gap_signal_summary,
        "product_line_cannibalization_summary": product_line_cannibalization,
        "action_plan": action_plan,
        "not_supported_reasons": [
            "缺少广告、库存、促销、毛利和线下渠道数据，不能判断这些因素。",
            "卖点价值为可观测贡献估计，不代表严格因果。",
            "累计销量只作为展示上下文，不用于判断谁卖得好或差。",
        ],
        "method_note_cn": "先判断目标是否在可比线上样本中真的偏弱，再按价值棒拆成用户愿付价值、价格攫取、竞品替代、同品牌产品线分流、证据风险和数据边界；原因和建议只使用现有 CatForge 分析结果。",
        "candidate_pool": ((candidates.get("result") or {}).get("candidate_search") or {}),
    }


def _low_sales_target_summary(target: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    fact_brief = (fact.get("result") or {}).get("fact_brief") or {}
    sections = fact_brief.get("sections") or {}
    market = sections.get("market") or {}
    return {
        "identity": target,
        "market_position": market.get("market_position") or {},
        "market_metrics": market.get("market_metrics") or {},
        "primary_semantics": {
            "primary_user_task_code": (sections.get("user_task") or {}).get("primary_user_task_code"),
            "primary_target_group_code": (sections.get("target_group") or {}).get("primary_target_group_code"),
            "primary_battlefield_code": (sections.get("value_battlefield") or {}).get("primary_battlefield_code"),
        },
    }


def _low_sales_pairwise_rows(pairwise_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in pairwise_results:
        payload = ((result.get("result") or {}).get("why_sales_diff") or {})
        candidate = payload.get("candidate") or {}
        sales = payload.get("sales_overlap") or {}
        comparison = sales.get("comparison") or {}
        method = str(sales.get("method") or "")
        overlap_week_count = int(sales.get("overlap_week_count") or 0)
        sales_ratio = _decimal(comparison.get("target_vs_candidate_avg_weekly_volume_ratio"))
        amount_ratio = _decimal(comparison.get("target_vs_candidate_avg_weekly_amount_ratio"))
        status, summary = _low_sales_pair_status(
            method=method,
            overlap_week_count=overlap_week_count,
            sales_ratio=sales_ratio,
            amount_ratio=amount_ratio,
        )
        rows.append(
            {
                "candidate_sku_code": candidate.get("sku_code") or sales.get("candidate_sku_code"),
                "candidate_name": _display_sku_name(candidate),
                "method": method,
                "overlap_week_count": overlap_week_count,
                "status": status,
                "sales_ratio": _float_or_none(sales_ratio),
                "amount_ratio": _float_or_none(amount_ratio),
                "summary_cn": summary,
                "sales_overlap": sales,
            }
        )
    return rows


def _low_sales_pair_status(
    *,
    method: str,
    overlap_week_count: int,
    sales_ratio: Decimal | None,
    amount_ratio: Decimal | None,
) -> tuple[str, str]:
    if method != "pairwise_overlap_active_week_average" or overlap_week_count < MIN_OVERLAP_WEEKS or sales_ratio is None or amount_ratio is None:
        return "uncertain", "重叠在售周不足或使用回退口径，不能稳定判断。"
    if sales_ratio < LOW_SALES_RATIO_THRESHOLD and amount_ratio < LOW_AMOUNT_RATIO_THRESHOLD:
        return "weak", "目标 SKU 在重叠在售周的周均销量和周均销额均弱于该竞品。"
    if sales_ratio < LOW_SALES_RATIO_THRESHOLD and amount_ratio >= LOW_AMOUNT_RATIO_THRESHOLD:
        return "price_supported_niche", "目标 SKU 周均销量偏弱，但销额承接不弱，可能是高价小众或高价销额承接。"
    if sales_ratio >= NOT_WEAK_SALES_RATIO_THRESHOLD or amount_ratio >= NOT_WEAK_AMOUNT_RATIO_THRESHOLD:
        return "not_weak", "目标 SKU 在重叠在售周的销量或销额不弱于该竞品。"
    return "mixed", "目标 SKU 与该竞品差距不大，但还不足以判定明显强弱。"


def _low_sales_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if row.get("status") not in {"uncertain"}]
    weak_count = sum(1 for row in usable if row.get("status") == "weak")
    not_weak_count = sum(1 for row in usable if row.get("status") in {"not_weak", "price_supported_niche"})
    if len(usable) < 2:
        status = "uncertain"
        confidence = "low"
        basis = "可用重叠在售周竞品对比不足，不能稳定判断是否真的低销量。"
    elif Decimal(weak_count) / Decimal(len(usable)) >= Decimal("0.6000"):
        status = "weak"
        confidence = "medium"
        basis = "多数重点竞品在重叠在售周的周均销量或销额明显高于目标。"
    elif Decimal(not_weak_count) / Decimal(len(usable)) >= Decimal("0.6000"):
        status = "not_weak"
        confidence = "medium"
        basis = "目标对多数重点竞品的周均销量或销额不弱。"
    else:
        status = "mixed"
        confidence = "medium"
        basis = "目标对部分竞品偏弱、对部分竞品不弱。"
    return {
        "status": status,
        "confidence": confidence,
        "basis_cn": basis,
        "comparison_count": len(usable),
        "weak_against_count": weak_count,
        "not_weak_against_count": not_weak_count,
        "uncertain_against_count": sum(1 for row in rows if row.get("status") == "uncertain"),
        "comparison_rows": rows,
    }


def _low_sales_claim_value_summary(premium_payload: dict[str, Any], claim_gap_payload: dict[str, Any]) -> dict[str, Any]:
    rows = _claim_value_rows(premium_payload)
    summary = {
        "premium_claims": _claims_by_category(rows, "高溢价卖点"),
        "share_conversion_claims": _claims_by_category(rows, "份额转化卖点"),
        "customer_value_claims": _claims_by_category(rows, "客户获得价值卖点"),
        "threshold_claims": _claims_by_category(rows, "门槛卖点"),
        "pending_claims": _claims_by_category(rows, "待激活卖点"),
        "brand_claims": _claims_by_category(rows, "厂家主张卖点"),
        "intercept_claims": _claims_by_category(rows, "竞品拦截卖点"),
        "price_pressure_claims": _claims_by_category(rows, "价格压力卖点"),
        "sample_insufficient_claims": _claims_by_category(rows, "样本不足待复核"),
    }
    gap_rows = [row for row in claim_gap_payload.get("target_opportunity_or_drag_claims") or [] if isinstance(row, dict)]
    candidate_rows = [row for row in claim_gap_payload.get("candidate_positive_claims_missing_on_target") or [] if isinstance(row, dict)]
    for row in [*gap_rows, *candidate_rows]:
        item = _claim_item(row)
        if item not in summary["intercept_claims"]:
            summary["intercept_claims"].append(item)
    return summary


def _claim_value_rows(premium_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in premium_payload.get("m12c_quantified_claim_values", {}).get("sku_level_claim_values") or [] if isinstance(row, dict)]
    if rows:
        return rows
    return [row for row in premium_payload.get("m12c_quantified_claim_values", {}).get("claim_values") or [] if isinstance(row, dict)]


def _claims_by_category(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [_claim_item(row) for row in rows if str(row.get("business_claim_type_cn") or row.get("business_value_label") or "") == category]


def _claim_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_code": row.get("claim_code"),
        "claim_name": row.get("claim_name") or row.get("claim_code"),
        "business_claim_type_cn": row.get("business_claim_type_cn") or row.get("business_value_label"),
        "summary_cn": row.get("evidence_summary_cn") or row.get("reason_cn") or "",
    }


def _low_sales_battlefield_summary(battlefield_payload: dict[str, Any]) -> dict[str, Any]:
    gaps = battlefield_payload.get("opportunity_gaps") or {}
    return {
        "established_battlefields": gaps.get("established_battlefields") or [],
        "opportunity_battlefields": gaps.get("opportunity_battlefields") or [],
        "user_observed_battlefields": gaps.get("user_observed_battlefields") or [],
        "drag_factor_battlefields": gaps.get("drag_factor_battlefields") or [],
        "related_battlefield_spaces": battlefield_payload.get("related_battlefield_spaces") or [],
    }


def _low_sales_gap_signal_summary(opportunity_gaps: dict[str, Any]) -> dict[str, Any]:
    return {
        "price_gap_signals": opportunity_gaps.get("price_gap_signals") or [],
        "param_gap_signals": opportunity_gaps.get("param_gap_signals") or [],
        "claim_gap_signals": opportunity_gaps.get("claim_gap_signals") or [],
        "comment_gap_signals": opportunity_gaps.get("comment_gap_signals") or [],
        "semantic_gap_signals": opportunity_gaps.get("semantic_gap_signals") or [],
    }


def _low_sales_product_line_cannibalization(
    *,
    candidates: dict[str, Any],
    target_summary: dict[str, Any],
    claim_value_summary: dict[str, Any],
) -> dict[str, Any]:
    search = ((candidates.get("result") or {}).get("candidate_search") or {})
    target_market = search.get("target_market") or {}
    target_identity = target_summary.get("identity") or {}
    target_brand = str(target_market.get("brand_name") or target_identity.get("brand_name") or "").strip()
    target_sku = str(target_market.get("sku_code") or target_identity.get("sku_code") or "").strip()
    target_price = _decimal(target_market.get("price_wavg") or (target_summary.get("market_metrics") or {}).get("price_wavg"))
    target_avg_weekly = _decimal(target_market.get("avg_weekly_sales_volume") or (target_summary.get("market_metrics") or {}).get("avg_weekly_sales_volume"))
    target_band = str(target_market.get("price_band_in_size_tier") or "").strip()
    target_has_clear_anchor = _positive_claim_count(claim_value_summary) > 0
    rows: list[dict[str, Any]] = []
    for row in [item for item in search.get("candidates") or [] if isinstance(item, dict)]:
        if not target_brand or str(row.get("brand_name") or "").strip() != target_brand:
            continue
        if str(row.get("sku_code") or "").strip() == target_sku:
            continue
        candidate_price = _decimal(row.get("price_wavg"))
        candidate_avg_weekly = _decimal(row.get("avg_weekly_sales_volume"))
        price_gap = _decimal(row.get("price_gap_to_target"))
        if price_gap is None and candidate_price is not None and target_price is not None:
            price_gap = candidate_price - target_price
        if price_gap is None or price_gap > 0:
            continue
        if target_avg_weekly is None or candidate_avg_weekly is None or candidate_avg_weekly < target_avg_weekly * Decimal("1.20"):
            continue
        sales_ratio = _safe_ratio(candidate_avg_weekly, target_avg_weekly)
        rows.append(
            {
                "sku_code": row.get("sku_code"),
                "brand_name": row.get("brand_name"),
                "model_name": row.get("model_name"),
                "price_wavg": row.get("price_wavg"),
                "target_price_wavg": _float_or_none(target_price),
                "price_gap_to_target": _float_or_none(price_gap),
                "price_relation_cn": f"同品牌低价 SKU，均价约低{_yuan_text(abs(price_gap))}。",
                "avg_weekly_sales_volume": row.get("avg_weekly_sales_volume"),
                "target_avg_weekly_sales_volume": _float_or_none(target_avg_weekly),
                "sales_ratio_to_target": _float_or_none(sales_ratio),
                "price_band_in_size_tier": row.get("price_band_in_size_tier"),
                "target_price_band_in_size_tier": target_band,
                "summary_cn": f"{row.get('brand_name') or target_brand} {row.get('model_name') or row.get('sku_code')} 均价约低{_yuan_text(abs(price_gap))}，周均销量约为目标的{_ratio_text(_float_or_none(sales_ratio)) or '更高'}。",
            }
        )
    rows = sorted(rows, key=lambda row: (-(row.get("sales_ratio_to_target") or 0), abs(row.get("price_gap_to_target") or 0), str(row.get("sku_code") or "")))
    if not rows:
        return {
            "status": "unknown",
            "candidate_count": 0,
            "target_has_clear_anchor": target_has_clear_anchor,
            "candidates": [],
            "summary_cn": "没有发现同品牌、同尺寸、更低价且周均销量明显强于目标的分流信号。",
        }
    anchor_note = "且目标缺少足够清晰的价差锚点" if not target_has_clear_anchor else "需要继续判断目标正向卖点是否足以解释价差"
    return {
        "status": "possible",
        "candidate_count": len(rows),
        "target_has_clear_anchor": target_has_clear_anchor,
        "candidates": rows[:5],
        "summary_cn": f"发现 {len(rows)} 个同品牌低价高销量 SKU，{anchor_note}，存在产品线分流可能。",
    }


def _low_sales_claim_compare_by_sku(claim_compare_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in claim_compare_results:
        payload = ((item.get("result") or {}).get("claim_value_compare") or {}) if isinstance(item, dict) else {}
        candidate_sku = str(payload.get("candidate_sku_code") or ((item.get("result") or {}).get("candidate") or {}).get("sku_code") or "")
        if candidate_sku and payload:
            result[candidate_sku] = payload
    return result


def _low_sales_compare_claims(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    claims = [row for row in payload.get(key) or [] if isinstance(row, dict)]
    claims = sorted(claims, key=_low_sales_compare_claim_sort_key)
    return [_low_sales_compare_claim_summary(row) for row in claims[:8]]


def _low_sales_compare_claim_sort_key(row: dict[str, Any]) -> tuple[float, float, str]:
    candidate = row.get("candidate") or {}
    contribution = candidate.get("estimated_contribution") or {}
    pool_effect = candidate.get("pool_effect") or {}
    contribution_share = _float_or_none(_decimal(contribution.get("contribution_share_in_sku"))) or 0.0
    score = _float_or_none(_decimal(candidate.get("claim_value_score"))) or 0.0
    effect = abs(_float_or_none(_decimal(pool_effect.get("pool_claim_weekly_sales_delta_abs"))) or 0.0) + abs(_float_or_none(_decimal(pool_effect.get("pool_claim_price_delta_abs"))) or 0.0) / 100
    return (-contribution_share, -score - effect / 100, str(row.get("claim_code") or ""))


def _low_sales_compare_claim_summary(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("candidate") or {}
    target = row.get("target") or {}
    item = {
        "claim_code": row.get("claim_code"),
        "claim_name": row.get("claim_name") or candidate.get("claim_name") or target.get("claim_name") or row.get("claim_code"),
        "relation": row.get("relation"),
        "target_role": target.get("claim_value_role"),
        "target_business_claim_type_cn": target.get("business_claim_type_cn"),
        "candidate_role": candidate.get("claim_value_role"),
        "candidate_business_claim_type_cn": candidate.get("business_claim_type_cn"),
        "candidate_business_value_label": candidate.get("business_value_label"),
        "candidate_claim_source_type_cn": candidate.get("claim_source_type_cn"),
        "candidate_claim_value_score": candidate.get("claim_value_score"),
        "candidate_parameter_competitiveness": candidate.get("parameter_competitiveness") or {},
        "candidate_evidence_strength": candidate.get("evidence_strength") or {},
        "candidate_pool_effect": candidate.get("pool_effect") or {},
        "candidate_estimated_contribution": candidate.get("estimated_contribution") or {},
    }
    item["candidate_market_signal_cn"] = _claim_market_signal_text(item)
    item["candidate_parameter_level_cn"] = _claim_parameter_level_text(item)
    item["downgrade_reason_cn"] = _claim_parameter_downgrade_text(item).removeprefix("限制：")
    item["effect_cn"] = _claim_effect_text(item)
    return item


def _specific_competitor_gap_summary(
    *,
    candidate_name: str,
    candidate_advantage_claims: list[dict[str, Any]],
    target_advantage_claims: list[dict[str, Any]],
) -> str:
    if not candidate_advantage_claims:
        return ""
    claim_names = "、".join(str(row.get("claim_name") or row.get("claim_code")) for row in candidate_advantage_claims[:4])
    target_text = "，而本品没有可抵消的正向卖点信号" if not target_advantage_claims else f"，本品可抵消卖点信号为{'、'.join(str(row.get('claim_name') or row.get('claim_code')) for row in target_advantage_claims[:3])}"
    return f"{candidate_name} 已成立、目标未形成正向对照的卖点信号包括{claim_names}{target_text}。"


def _low_sales_claim_compare_summary(competitor_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in competitor_evidence if row.get("candidate_advantage_claims")]
    top_competitor_claim_gaps: list[dict[str, Any]] = []
    top_claims: list[dict[str, Any]] = []
    for row in rows:
        top_competitor_claim_gaps.append(
            {
                "candidate_sku_code": row.get("candidate_sku_code"),
                "candidate_model_name": ((row.get("candidate") or {}).get("model_name") or row.get("candidate_name")),
                "candidate_name": row.get("candidate_name"),
                "candidate_advantage_claims": row.get("candidate_advantage_claims") or [],
                "target_advantage_claims": row.get("target_advantage_claims") or [],
                "specific_gap_summary_cn": row.get("specific_gap_summary_cn") or "",
            }
        )
        for claim in row.get("candidate_advantage_claims") or []:
            top_claims.append(
                {
                    "candidate_sku_code": row.get("candidate_sku_code"),
                    "candidate_name": row.get("candidate_name"),
                    "claim_code": claim.get("claim_code"),
                    "claim_name": claim.get("claim_name"),
                    "candidate_market_signal_cn": claim.get("candidate_market_signal_cn") or _claim_market_signal_text(claim),
                    "candidate_parameter_level_cn": claim.get("candidate_parameter_level_cn") or _claim_parameter_level_text(claim),
                    "downgrade_reason_cn": claim.get("downgrade_reason_cn") or "",
                    "effect_cn": claim.get("effect_cn") or _claim_effect_text(claim),
                }
            )
    return {
        "competitor_with_candidate_advantage_count": len(rows),
        "top_competitor_claim_gaps": top_competitor_claim_gaps[:5],
        "top_candidate_advantage_claims": top_claims[:12],
        "summary_cn": "；".join(row.get("specific_gap_summary_cn") for row in rows[:3] if row.get("specific_gap_summary_cn")),
        "method_note_cn": "市场观测角色不等于卖点天然强弱，必须和参数/事实口径一起展示。",
    }


def _low_sales_competitor_evidence(
    competitor_set: dict[str, Any],
    pairwise_rows: list[dict[str, Any]],
    claim_gap_payload: dict[str, Any],
    claim_compare_by_sku: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    competitors = (((competitor_set.get("result") or {}).get("competitor_set") or {}).get("candidates") or [])
    pair_by_sku = {row.get("candidate_sku_code"): row for row in pairwise_rows}
    candidate_gap_claims = [row for row in claim_gap_payload.get("candidate_positive_claims_missing_on_target") or [] if isinstance(row, dict)]
    gap_names = "、".join(str(row.get("claim_name") or row.get("claim_code")) for row in candidate_gap_claims[:4])
    evidence: list[dict[str, Any]] = []
    for item in competitors[:5]:
        candidate = item.get("candidate") or {}
        sku_code = candidate.get("sku_code")
        pair = pair_by_sku.get(sku_code) or {}
        claim_compare = claim_compare_by_sku.get(str(sku_code or "")) or {}
        sales = pair.get("sales_overlap") or {}
        target_sales = sales.get("target") or {}
        candidate_sales = sales.get("candidate") or {}
        candidate_advantage_claims = _low_sales_compare_claims(claim_compare, "candidate_advantage_claims")
        target_advantage_claims = _low_sales_compare_claims(claim_compare, "target_advantage_claims")
        evidence.append(
            {
                "rank": item.get("rank"),
                "candidate": candidate,
                "candidate_sku_code": sku_code,
                "candidate_name": _display_sku_name(candidate),
                "pairwise_sales_status": pair.get("status") or "uncertain",
                "sales_summary_cn": pair.get("summary_cn") or "",
                "sales_ratio": pair.get("sales_ratio"),
                "amount_ratio": pair.get("amount_ratio"),
                "overlap_week_count": pair.get("overlap_week_count"),
                "target_avg_weekly_sales_volume": target_sales.get("avg_weekly_sales_volume_on_overlap_weeks"),
                "candidate_avg_weekly_sales_volume": candidate_sales.get("avg_weekly_sales_volume_on_overlap_weeks"),
                "target_avg_weekly_sales_amount": target_sales.get("avg_weekly_sales_amount_on_overlap_weeks"),
                "candidate_avg_weekly_sales_amount": candidate_sales.get("avg_weekly_sales_amount_on_overlap_weeks"),
                "price_relation_cn": _competitor_price_summary(candidate),
                "semantic_overlap_summary_cn": _semantic_overlap_summary(item.get("semantic_overlap") or {}),
                "candidate_advantage_claims": candidate_advantage_claims,
                "target_advantage_claims": target_advantage_claims,
                "specific_gap_summary_cn": _specific_competitor_gap_summary(
                    candidate_name=_display_sku_name(candidate),
                    candidate_advantage_claims=candidate_advantage_claims,
                    target_advantage_claims=target_advantage_claims,
                ),
                "claim_gap_summary_cn": f"竞品侧拦截或机会缺口：{gap_names}。" if gap_names else "",
                "evidence_refs": [],
            }
        )
    return evidence


def _low_sales_reason_ranking(
    *,
    target_summary: dict[str, Any],
    sales_status: dict[str, Any],
    claim_value_summary: dict[str, Any],
    battlefield_summary: dict[str, Any],
    gap_signal_summary: dict[str, Any],
    competitor_evidence: list[dict[str, Any]],
    product_line_cannibalization: dict[str, Any],
) -> list[dict[str, Any]]:
    reasons = [
        _reason_specific_competitor_value_gap(sales_status, competitor_evidence),
        _reason_price_value_mismatch(target_summary, sales_status, claim_value_summary, gap_signal_summary, competitor_evidence),
        _reason_weak_customer_wtp(sales_status, claim_value_summary, battlefield_summary),
        _reason_claim_not_activated(claim_value_summary, gap_signal_summary),
        _reason_competitor_intercept(sales_status, competitor_evidence, claim_value_summary),
        _reason_battlefield_target_mismatch(battlefield_summary, gap_signal_summary),
        _reason_same_brand_cannibalization(sales_status, product_line_cannibalization),
        _reason_experience_or_evidence_risk(gap_signal_summary),
    ]
    reasons = [row for row in reasons if row["evidence_strength"] > 0]
    reasons = sorted(reasons, key=_low_sales_reason_sort_key)
    for index, row in enumerate(reasons, start=1):
        row["rank"] = index
        row.pop("score", None)
    return reasons


def _low_sales_reason_sort_key(row: dict[str, Any]) -> tuple[int, Decimal, str]:
    priority = 0 if row.get("reason_type") == "specific_competitor_value_gap" else 1
    return (priority, -row["score"], str(row.get("reason_type") or ""))


def _reason_specific_competitor_value_gap(
    sales_status: dict[str, Any],
    competitor_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = [
        row
        for row in competitor_evidence
        if row.get("pairwise_sales_status") == "weak" and row.get("candidate_advantage_claims")
    ]
    claim_count = sum(len(row.get("candidate_advantage_claims") or []) for row in rows)
    evidence_strength = min(Decimal("1"), Decimal("0.30") * len(rows) + Decimal("0.06") * claim_count)
    observation_points = _specific_competitor_value_gap_points(rows)
    root_cause = _specific_competitor_value_gap_root_cause(rows)
    return _reason_payload(
        reason_type="specific_competitor_value_gap",
        reason_name_cn="关键购买锚点被竞品占位",
        value_stick_position="competitor_alternative",
        evidence_strength=evidence_strength,
        summary_cn=root_cause,
        value_stick_effect_cn="强竞品把用户愿付价值绑定到更具体的收益锚点，本品没有同等证据时，用户剩余价值会流向竞品。",
        detail_points=observation_points,
        action_keys=["intercept_claim_defense", "content_proof_build", "competitor_comparison_message"],
        sales_status=sales_status,
        evidence_refs=_specific_competitor_value_gap_refs(rows),
        observation_points=observation_points,
        root_cause_cn=root_cause,
        value_stick_mechanism_cn="价值棒上端不是被“电视”这个大类抬高，而是被芯片、影音认证、护眼、游戏低延迟、HDR、高刷等可验证收益抬高；当竞品占住这些收益锚点而本品缺位时，本品的愿付价值自然上不去。",
        decision_implication_cn="先不要泛泛降价或泛泛补卖点；要逐项判断这些竞品优势中哪些本品真实具备但没讲清，哪些本品确实不具备。前者补证据和页面表达，后者避开正面战场或用价格/权益补偿。",
        validation_cn="对每个强竞品优势卖点做页面证据补强或正面对比测试，观察目标竞品搜索词、详情页跳出、加购和转化是否改善。",
    )


def _reason_price_value_mismatch(
    target_summary: dict[str, Any],
    sales_status: dict[str, Any],
    claim_value_summary: dict[str, Any],
    gap_signal_summary: dict[str, Any],
    competitor_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    signals = [row for row in gap_signal_summary.get("price_gap_signals") or [] if isinstance(row, dict)]
    pressure_claims = claim_value_summary.get("price_pressure_claims") or []
    low_price_competitors = [row for row in competitor_evidence if row.get("pairwise_sales_status") == "weak" and "更低" in str(row.get("price_relation_cn") or "")]
    evidence_strength = min(Decimal("1"), Decimal("0.25") * len(signals) + Decimal("0.25") * len(pressure_claims) + Decimal("0.20") * len(low_price_competitors))
    detail_points = [
        *_market_position_detail_points(target_summary),
        *_competitor_price_pressure_points(low_price_competitors[:3]),
        *_claim_detail_points(pressure_claims[:3], prefix="价格压力卖点"),
        *_signal_detail_points(signals[:3]),
    ]
    positive_claim_count = _positive_claim_count(claim_value_summary)
    return _reason_payload(
        reason_type="price_value_mismatch",
        reason_name_cn="高有效价格未被价值证据承接",
        value_stick_position="price_capture",
        evidence_strength=evidence_strength,
        summary_cn=_price_value_root_cause(positive_claim_count=positive_claim_count, low_price_competitors=low_price_competitors),
        value_stick_effect_cn="价格端拿走了较多用户价值，但用户愿付价值和竞品替代压力没有同步支撑，价值棒中间空间被压窄。",
        detail_points=detail_points,
        action_keys=["price_band_test", "value_message_reframe"],
        sales_status=sales_status,
        evidence_refs=[*_signal_refs(signals[:3]), *_claim_refs(pressure_claims[:3])],
        observation_points=detail_points,
        root_cause_cn=_price_value_root_cause(positive_claim_count=positive_claim_count, low_price_competitors=low_price_competitors),
        value_stick_mechanism_cn="用户愿付价值没有被证据抬高到当前价格之上，价格端先拿走价值，用户剩余价值不足，于是更容易转向低价或更确定的替代品。",
        decision_implication_cn="这不是直接永久降价结论；应先做券后价、权益包或套装 A/B 测试。如果销量弹性明显，说明有效价格需要下调或重设价格带；如果弹性不明显，再转向价值证明和定位重构。",
        validation_cn="需要补充同流量、同曝光下的券后价转化率和加购率，区分价格弹性问题和流量质量问题。",
    )


def _reason_weak_customer_wtp(
    sales_status: dict[str, Any],
    claim_value_summary: dict[str, Any],
    battlefield_summary: dict[str, Any],
) -> dict[str, Any]:
    positive_count = sum(len(claim_value_summary.get(key) or []) for key in ("premium_claims", "share_conversion_claims", "customer_value_claims"))
    established_count = len(battlefield_summary.get("established_battlefields") or [])
    positive_claims = [*(claim_value_summary.get("premium_claims") or []), *(claim_value_summary.get("share_conversion_claims") or []), *(claim_value_summary.get("customer_value_claims") or [])]
    evidence_strength = Decimal("0")
    if positive_count == 0:
        evidence_strength += Decimal("0.35")
    if established_count == 0:
        evidence_strength += Decimal("0.25")
    if sales_status.get("status") == "weak":
        evidence_strength += Decimal("0.20")
    detail_points = []
    if positive_count == 0:
        detail_points.append("没有看到可稳定支撑溢价、份额转化或客户获得价值的正向卖点，用户愿付价值缺少明确支点。")
    else:
        detail_points.append(f"正向卖点主要集中在 {_claim_names_joined(positive_claims[:4])}，但还需要看这些卖点是否能覆盖当前价格。")
    if established_count == 0:
        detail_points.append("当前没有稳定成立的价值战场，产品支付理由没有被主场景持续验证。")
    if sales_status.get("status") == "weak":
        detail_points.append("重叠在售周销量已经弱于多数重点竞品，说明用户没有用购买行为充分验证当前价值主张。")
    return _reason_payload(
        reason_type="weak_customer_wtp",
        reason_name_cn="购买任务和支付理由没有被证据化",
        value_stick_position="customer_wtp",
        evidence_strength=min(Decimal("1"), evidence_strength),
        summary_cn=_customer_wtp_root_cause(positive_count=positive_count, established_count=established_count),
        value_stick_effect_cn="用户愿付价值没有被抬高到足够位置，价格即使不变也会显得偏贵。",
        detail_points=detail_points,
        action_keys=["focus_validated_claims", "reframe_primary_scene"],
        sales_status=sales_status,
        evidence_refs=[],
        observation_points=detail_points,
        root_cause_cn=_customer_wtp_root_cause(positive_count=positive_count, established_count=established_count),
        value_stick_mechanism_cn="价值棒上端没有被具体用户任务和可验证收益抬高，用户无法把价格换算成确定收益，因此同样预算会流向更容易理解的替代品。",
        decision_implication_cn="不要继续写泛化的高端、画质、智能等大词；先选一个明确购买任务和客群，把对应卖点补成可证明的收益。若找不到能支撑当前价格的任务，应下调定位或避开高价走量池。",
        validation_cn="需要验证哪一个用户任务能带来更高点击、加购或转化，再决定主卖点和主战场。",
    )


def _reason_claim_not_activated(claim_value_summary: dict[str, Any], gap_signal_summary: dict[str, Any]) -> dict[str, Any]:
    pending = claim_value_summary.get("pending_claims") or []
    brand = claim_value_summary.get("brand_claims") or []
    claim_signals = [row for row in gap_signal_summary.get("claim_gap_signals") or [] if isinstance(row, dict)]
    evidence_strength = min(Decimal("1"), Decimal("0.18") * len(pending) + Decimal("0.15") * len(brand) + Decimal("0.20") * len(claim_signals))
    detail_points = [
        *_claim_detail_points(pending[:4], prefix="待激活卖点"),
        *_claim_detail_points(brand[:3], prefix="厂家主张卖点"),
        *_signal_detail_points(claim_signals[:3]),
    ]
    return _reason_payload(
        reason_type="claim_not_activated",
        reason_name_cn="卖点停留在表达层，没有变成购买证据",
        value_stick_position="customer_wtp",
        evidence_strength=evidence_strength,
        summary_cn="产品能力或厂家表达没有被用户评论、参数差异和市场表现共同证明，用户看不到为它多付钱的证据。",
        value_stick_effect_cn="产品能力没有转化为用户感知，用户愿付价值提升不足。",
        detail_points=detail_points,
        action_keys=["claim_page_reorder", "content_proof_build"],
        sales_status={},
        evidence_refs=[*_claim_refs(pending[:3]), *_claim_refs(brand[:2]), *_signal_refs(claim_signals[:2])],
        observation_points=detail_points,
        root_cause_cn="产品能力或厂家表达没有被用户评论、参数差异和市场表现共同证明，用户看不到为它多付钱的证据。",
        value_stick_mechanism_cn="卖点没有转化为用户可感知收益，愿付价值不会上移，价格端就缺少承接。",
        decision_implication_cn="先重排详情页和导购话术，只保留能被证据支撑的主卖点；缺证据的卖点先补测评、评论和场景内容，不宜直接放在首屏承担转化。",
        validation_cn="验证主卖点替换前后的点击率、详情页停留、加购和转化变化。",
    )


def _reason_competitor_intercept(
    sales_status: dict[str, Any],
    competitor_evidence: list[dict[str, Any]],
    claim_value_summary: dict[str, Any],
) -> dict[str, Any]:
    weak_competitors = [row for row in competitor_evidence if row.get("pairwise_sales_status") == "weak"]
    intercept_claims = claim_value_summary.get("intercept_claims") or []
    evidence_strength = min(Decimal("1"), Decimal("0.25") * len(weak_competitors) + Decimal("0.20") * len(intercept_claims))
    detail_points = [
        *_competitor_intercept_points(competitor_evidence, weak_competitors),
        *_claim_detail_points(intercept_claims[:3], prefix="竞品拦截卖点"),
    ]
    return _reason_payload(
        reason_type="competitor_intercept",
        reason_name_cn="同池替代品降低了用户切换成本",
        value_stick_position="competitor_alternative",
        evidence_strength=evidence_strength,
        summary_cn="真正原因不是竞品卖得好，而是目标 SKU 在同购买池没有形成足以抵消价差或风险的差异化选择理由，用户换到替代品的成本太低。",
        value_stick_effect_cn="用户的替代选择足够强，本品能保留的成交价值被竞品拿走。",
        detail_points=detail_points,
        action_keys=["competitor_comparison_message", "intercept_claim_defense"],
        sales_status=sales_status,
        evidence_refs=[{"source": "competitor", "summary_cn": row.get("candidate_name")} for row in weak_competitors[:3]] + _claim_refs(intercept_claims[:3]),
        observation_points=detail_points,
        root_cause_cn="真正原因不是竞品卖得好，而是目标 SKU 在同购买池没有形成足以抵消价差或风险的差异化选择理由，用户换到替代品的成本太低。",
        value_stick_mechanism_cn="替代品把用户的外部选项抬高，本品的可保留成交价值被压低；如果本品没有清晰防守点，用户剩余价值会被竞品拿走。",
        decision_implication_cn="先挑最强的 1-2 个竞品写清楚“为什么买我而不是它”。如果说不出可验证优势，就不要正面硬打该购买池，应改价格带、权益包或战场定位。",
        validation_cn="验证正面对比内容上线后，目标竞品搜索词、详情页跳出、加购和转化是否改善。",
    )


def _reason_battlefield_target_mismatch(battlefield_summary: dict[str, Any], gap_signal_summary: dict[str, Any]) -> dict[str, Any]:
    opportunities = battlefield_summary.get("opportunity_battlefields") or []
    drags = battlefield_summary.get("drag_factor_battlefields") or []
    semantic_signals = [row for row in gap_signal_summary.get("semantic_gap_signals") or [] if isinstance(row, dict)]
    evidence_strength = min(Decimal("1"), Decimal("0.20") * len(opportunities) + Decimal("0.25") * len(drags) + Decimal("0.15") * len(semantic_signals))
    detail_points = [
        *_dimension_detail_points(opportunities[:3], prefix="机会战场"),
        *_dimension_detail_points(drags[:3], prefix="拖后腿战场"),
        *_signal_detail_points(semantic_signals[:4]),
    ]
    return _reason_payload(
        reason_type="battlefield_target_mismatch",
        reason_name_cn="主战场没有收敛到一个确定购买场景",
        value_stick_position="customer_wtp",
        evidence_strength=evidence_strength,
        summary_cn="价值表达没有收敛到一个确定购买场景和人群，产品不知道该为谁解决什么高价值问题。",
        value_stick_effect_cn="产品没有站稳最能抬高愿付价值的用户任务和场景，价值主张容易被同池竞品改写。",
        detail_points=detail_points,
        action_keys=["reframe_primary_scene", "opportunity_battlefield_content"],
        sales_status={},
        evidence_refs=[*_dimension_refs(opportunities[:3]), *_dimension_refs(drags[:3]), *_signal_refs(semantic_signals[:2])],
        observation_points=detail_points,
        root_cause_cn="价值表达没有收敛到一个确定购买场景和人群，产品不知道该为谁解决什么高价值问题。",
        value_stick_mechanism_cn="没有明确任务和客群时，用户愿付价值无法被场景收益抬高，竞品可以用更清晰的场景锚点改写比较标准。",
        decision_implication_cn="先选一个机会战场做小范围内容和投放验证，不要同时覆盖多个泛场景；验证成立后再把产品页、卖点和竞品对比都围绕该战场重排。",
        validation_cn="验证不同战场内容包的点击、收藏、加购和成交差异。",
    )


def _reason_same_brand_cannibalization(
    sales_status: dict[str, Any],
    product_line_cannibalization: dict[str, Any],
) -> dict[str, Any]:
    rows = [row for row in product_line_cannibalization.get("candidates") or [] if isinstance(row, dict)]
    evidence_strength = min(Decimal("1"), Decimal("0.30") * len(rows))
    if rows and not product_line_cannibalization.get("target_has_clear_anchor"):
        evidence_strength += Decimal("0.25")
    if rows and sales_status.get("status") == "weak":
        evidence_strength += Decimal("0.15")
    evidence_strength = min(Decimal("1"), evidence_strength)
    detail_points = _same_brand_cannibalization_points(rows)
    root_cause = _same_brand_cannibalization_root_cause(rows)
    return _reason_payload(
        reason_type="same_brand_cannibalization",
        reason_name_cn="同品牌产品线分流",
        value_stick_position="product_line_cannibalization",
        evidence_strength=evidence_strength,
        summary_cn=root_cause,
        value_stick_effect_cn="同品牌低价 SKU 抬高了用户的内部替代选项，本品如果没有明确价差理由，相对用户剩余价值会被自家低价款拿走。",
        detail_points=detail_points,
        action_keys=["product_line_value_separation", "product_line_price_ladder"],
        sales_status=sales_status,
        evidence_refs=[{"source": "same_size_price_candidates", "summary_cn": row.get("summary_cn") or row.get("sku_code")} for row in rows[:3]],
        observation_points=detail_points,
        root_cause_cn=root_cause,
        value_stick_mechanism_cn="用户想买本品牌时，低价高销量 SKU 提供了更高的内部替代剩余价值；如果本品的额外价值不清晰，价格差会变成转化阻力。",
        decision_implication_cn="需要明确本 SKU 与低价同品牌款的价差理由：能补证据就做内容和权益区隔，补不出就调整价格梯度或重新定义走量款/形象款关系。",
        validation_cn="验证同品牌低价款对本品详情页跳出、同店铺加购替代和转化流失的影响，并做价差权益包测试。",
    )


def _reason_experience_or_evidence_risk(gap_signal_summary: dict[str, Any]) -> dict[str, Any]:
    comment_signals = [row for row in gap_signal_summary.get("comment_gap_signals") or [] if isinstance(row, dict)]
    param_signals = [row for row in gap_signal_summary.get("param_gap_signals") or [] if isinstance(row, dict)]
    evidence_strength = min(Decimal("1"), Decimal("0.20") * len(comment_signals) + Decimal("0.15") * len(param_signals))
    detail_points = [*_signal_detail_points(comment_signals[:3]), *_signal_detail_points(param_signals[:3])]
    return _reason_payload(
        reason_type="experience_or_evidence_risk",
        reason_name_cn="体验风险或证据缺口削弱信任",
        value_stick_position="evidence_quality",
        evidence_strength=evidence_strength,
        summary_cn="评论、参数或样本证据存在不确定性，用户无法确认卖点是否真实可靠。",
        value_stick_effect_cn="证据不足会削弱用户对价值主张的信任，进一步压低愿付价值。",
        detail_points=detail_points,
        action_keys=["review_negative_feedback", "fill_evidence_gaps"],
        sales_status={},
        evidence_refs=[*_signal_refs(comment_signals[:3]), *_signal_refs(param_signals[:3])],
        observation_points=detail_points,
        root_cause_cn="评论、参数或样本证据存在不确定性，用户无法确认卖点是否真实可靠。",
        value_stick_mechanism_cn="信任不足会让用户对收益打折，愿付价值下降，即使参数看起来不错也难以支撑成交。",
        decision_implication_cn="先修复会影响成交信任的负向评论、参数冲突和缺失证据，再把相关卖点用于提价或主推。",
        validation_cn="补齐证据后复核负评率、咨询问题、退货原因和转化变化。",
    )


def _reason_payload(
    *,
    reason_type: str,
    reason_name_cn: str,
    value_stick_position: str,
    evidence_strength: Decimal,
    summary_cn: str,
    value_stick_effect_cn: str,
    detail_points: list[str],
    action_keys: list[str],
    sales_status: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    observation_points: list[str] | None = None,
    root_cause_cn: str | None = None,
    value_stick_mechanism_cn: str | None = None,
    decision_implication_cn: str | None = None,
    validation_cn: str | None = None,
) -> dict[str, Any]:
    severity = "high" if evidence_strength >= Decimal("0.70") else "medium" if evidence_strength >= Decimal("0.35") else "low" if evidence_strength > 0 else "unknown"
    sales_relevance = Decimal("0.20") if sales_status.get("status") == "weak" else Decimal("0.10") if sales_status.get("status") in {"mixed", "uncertain"} else Decimal("0.05")
    actionability = Decimal("0.75") if action_keys else Decimal("0.25")
    severity_weight = {"high": Decimal("1"), "medium": Decimal("0.65"), "low": Decimal("0.35"), "unknown": Decimal("0")}[severity]
    score = severity_weight * Decimal("0.35") + evidence_strength * Decimal("0.30") + sales_relevance + actionability * Decimal("0.15")
    return {
        "rank": 0,
        "reason_type": reason_type,
        "reason_name_cn": reason_name_cn,
        "severity": severity,
        "evidence_strength": _float_or_none(evidence_strength) or 0.0,
        "value_stick_position": value_stick_position,
        "summary_cn": summary_cn,
        "value_stick_effect_cn": value_stick_effect_cn,
        "observation_points": observation_points or detail_points,
        "root_cause_cn": root_cause_cn or summary_cn,
        "value_stick_mechanism_cn": value_stick_mechanism_cn or value_stick_effect_cn,
        "decision_implication_cn": decision_implication_cn or _default_reason_decision(action_keys),
        "validation_cn": validation_cn or "需要补充同口径流量、转化和成交证据后再确认。",
        "detail_points": detail_points,
        "evidence_refs": evidence_refs,
        "recommended_action_keys": action_keys,
        "score": score,
    }


def _low_sales_value_stick_summary(
    *,
    sales_status: dict[str, Any],
    reasons: list[dict[str, Any]],
    claim_value_summary: dict[str, Any],
    competitor_evidence: list[dict[str, Any]],
    product_line_cannibalization: dict[str, Any],
) -> dict[str, Any]:
    reason_types = {row.get("reason_type") for row in reasons[:3]}
    positive_claim_count = sum(len(claim_value_summary.get(key) or []) for key in ("premium_claims", "share_conversion_claims", "customer_value_claims"))
    product_line_status = str(product_line_cannibalization.get("status") or "unknown")
    return {
        "customer_wtp": {
            "status": "weak" if {"specific_competitor_value_gap", "weak_customer_wtp", "claim_not_activated", "battlefield_target_mismatch"} & reason_types else "medium" if positive_claim_count else "unknown",
            "summary_cn": "用户愿付价值由主战场、评论和卖点支付价值共同判断。",
        },
        "price_capture": {
            "status": "pressure" if "price_value_mismatch" in reason_types else "reasonable_or_unknown",
            "summary_cn": "价格是否过度攫取价值由价格分位、价格压力卖点和竞品低价压力共同判断。",
        },
        "competitor_alternative": {
            "status": "high" if {"specific_competitor_value_gap", "competitor_intercept"} & reason_types else "medium" if competitor_evidence else "unknown",
            "summary_cn": "竞品替代由同购买池、重叠周销量和卖点拦截共同判断。",
        },
        "product_line_cannibalization": {
            "status": product_line_status,
            "summary_cn": product_line_cannibalization.get("summary_cn") or "同品牌产品线分流信号不足。",
        },
        "evidence_risk": {
            "status": "high" if "experience_or_evidence_risk" in reason_types else "medium" if any(row.get("reason_type") == "experience_or_evidence_risk" for row in reasons) else "unknown",
            "summary_cn": "证据风险由评论负向、参数冲突、样本不足和卖点降级原因共同判断。",
        },
        "enterprise_side": {
            "status": "not_supported",
            "summary_cn": "当前缺少广告、库存、促销、毛利和渠道费用数据，不能判断企业侧和渠道侧原因。",
        },
    }


def _low_sales_action_plan(reasons: list[dict[str, Any]]) -> dict[str, Any]:
    action_defs = {
        "price_band_test": ("short_term_actions", "测试券后价、权益包或套装组合，让价格回到用户感知价值可以承接的位置。", "价格价值不匹配或低价竞品压力较明显。"),
        "value_message_reframe": ("short_term_actions", "把详情页和导购话术改成用户能感知的场景价值，而不是堆参数。", "需要增强用户对价格理由的理解。"),
        "focus_validated_claims": ("short_term_actions", "优先突出已经被评论和市场验证的画质、影音或大屏场景卖点。", "核心愿付价值需要先聚焦到已验证卖点。"),
        "claim_page_reorder": ("short_term_actions", "重排详情页主卖点，把待激活卖点降级为补充说明。", "部分厂家表达尚未形成用户支付理由。"),
        "competitor_comparison_message": ("short_term_actions", "增加与重点竞品的场景化对比表达，说明本品在同购买池中的选择理由。", "竞品可能在同战场中形成拦截。"),
        "content_proof_build": ("mid_term_actions", "补充测评、样张、评论证据和体验内容，让待激活卖点形成用户感知。", "卖点缺少评论或市场验证。"),
        "intercept_claim_defense": ("mid_term_actions", "对竞品已验证而本品弱表达的卖点做补证、补表达或明确绕开。", "竞品拦截点需要防守。"),
        "reframe_primary_scene": ("mid_term_actions", "重新定义主战场、主用户任务和主客群，减少价值表达错位。", "战场或客群存在机会和拖后腿信号。"),
        "opportunity_battlefield_content": ("mid_term_actions", "围绕机会战场补内容和证据，先做小范围转化验证。", "机会战场尚未稳定成立。"),
        "review_negative_feedback": ("mid_term_actions", "复核负向评论和参数冲突，先修复会拖累成交理由的体验问题。", "存在用户体验或证据风险。"),
        "fill_evidence_gaps": ("mid_term_actions", "补齐缺失参数、评论和样本证据，避免把未知当作无能力或强能力。", "诊断依赖证据完整度。"),
        "product_line_value_separation": ("short_term_actions", "明确本 SKU 与同品牌低价款的价差理由，补充权益、场景或参数证据区隔。", "同品牌低价高销量 SKU 可能分流目标。"),
        "product_line_price_ladder": ("mid_term_actions", "复盘同品牌同尺寸价格梯度，区分走量款、形象款和防守款的卖点与权益。", "产品线内部替代关系需要被重新定义。"),
        "product_line_reposition": ("high_cost_actions", "重新评估产品线价格梯度和 SKU 定位，区分形象款、走量款和防守款。", "如果短中期动作仍不能改善，需要调整产品线策略。"),
    }
    selected: dict[str, dict[str, Any]] = {}
    for reason in reasons[:5]:
        for key in reason.get("recommended_action_keys") or []:
            if key in selected or key not in action_defs:
                continue
            bucket, summary, why = action_defs[key]
            selected[key] = {
                "bucket": bucket,
                "action_key": key,
                "priority": len(selected) + 1,
                "cost_level": "low" if bucket == "short_term_actions" else "medium" if bucket == "mid_term_actions" else "high",
                "time_horizon": bucket.replace("_actions", ""),
                "summary_cn": summary,
                "why_cn": why,
                "expected_impact_cn": "降低对应原因对成交转化的影响，但不能直接估算销量增长。",
                "evidence_refs": reason.get("evidence_refs") or [],
                "not_supported_note_cn": "不能直接估算销量增长，因为缺广告、流量和转化链路。",
            }
    if reasons and "product_line_reposition" not in selected:
        bucket, summary, why = action_defs["product_line_reposition"]
        selected["product_line_reposition"] = {
            "bucket": bucket,
            "action_key": "product_line_reposition",
            "priority": len(selected) + 1,
            "cost_level": "high",
            "time_horizon": "high_cost",
            "summary_cn": summary,
            "why_cn": why,
            "expected_impact_cn": "用于长期修正定位和产品组合，不作为短期销量承诺。",
            "evidence_refs": [],
            "not_supported_note_cn": "需要补充成本、毛利、渠道和供应链数据后再决策。",
        }
    plan = {"short_term_actions": [], "mid_term_actions": [], "high_cost_actions": []}
    for action in selected.values():
        bucket = action.pop("bucket")
        plan[bucket].append(action)
    for bucket in plan:
        plan[bucket] = plan[bucket][:5]
    return plan


def _first_or_default(points: list[str], default: str) -> str:
    return points[0] if points else default


def _specific_competitor_value_gap_points(rows: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    for row in rows[:3]:
        name = str(row.get("candidate_name") or row.get("candidate_sku_code") or "强竞品")
        claims = [claim for claim in row.get("candidate_advantage_claims") or [] if isinstance(claim, dict)]
        if not claims:
            continue
        claim_phrases = [_claim_advantage_phrase(claim) for claim in claims[:4]]
        claim_phrases = [phrase for phrase in claim_phrases if phrase]
        if claim_phrases:
            points.append(f"{name} 已成立而目标缺失/弱化的具体卖点：{'；'.join(claim_phrases)}。")
        target_advantage = row.get("target_advantage_claims") or []
        if not target_advantage:
            points.append(f"对比 {name} 时，本品没有可抵消上述卖点的正向优势卖点。")
        overlap = row.get("overlap_week_count")
        target_avg = _volume_text(row.get("target_avg_weekly_sales_volume"))
        candidate_avg = _volume_text(row.get("candidate_avg_weekly_sales_volume"))
        if overlap and target_avg and candidate_avg:
            points.append(f"这些具体卖点对应的竞品在 {overlap} 个重叠周内周均 {candidate_avg} 台，本品周均 {target_avg} 台。")
    return points


def _specific_competitor_value_gap_root_cause(rows: list[dict[str, Any]]) -> str:
    top_claims: list[str] = []
    top_competitors: list[str] = []
    for row in rows[:2]:
        name = str(row.get("candidate_name") or row.get("candidate_sku_code") or "").strip()
        if name:
            top_competitors.append(name)
        for claim in row.get("candidate_advantage_claims") or []:
            claim_name = str((claim or {}).get("claim_name") or (claim or {}).get("claim_code") or "").strip()
            if claim_name and claim_name not in top_claims:
                top_claims.append(claim_name)
            if len(top_claims) >= 5:
                break
    competitor_text = "、".join(top_competitors[:2]) or "强竞品"
    claim_text = "、".join(top_claims[:5]) or "核心价值卖点"
    return f"具体原因是 {competitor_text} 在 {claim_text} 等购买锚点上有已成立的卖点信号，而目标 SKU 没有形成同等清晰的正向对照来解释为什么用户要选它。"


def _specific_competitor_value_gap_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in rows[:3]:
        for claim in (row.get("candidate_advantage_claims") or [])[:4]:
            refs.append(
                {
                    "source": "claim_value_compare",
                    "summary_cn": f"{row.get('candidate_name') or row.get('candidate_sku_code')}：{claim.get('claim_name') or claim.get('claim_code')}",
                }
            )
    return refs


def _claim_advantage_phrase(claim: dict[str, Any]) -> str:
    name = str(claim.get("claim_name") or claim.get("claim_code") or "").strip()
    if not name:
        return ""
    market_signal = _claim_market_signal_text(claim)
    parameter_level = _claim_parameter_level_text(claim)
    downgrade = _claim_parameter_downgrade_text(claim)
    source = _candidate_claim_source_text(claim)
    effect = _claim_effect_text(claim)
    evidence = _claim_evidence_text(claim)
    details = "，".join(part for part in (market_signal, parameter_level, downgrade, source, effect, evidence) if part)
    return f"{name}（{details}）" if details else name


def _candidate_claim_source_text(claim: dict[str, Any]) -> str:
    source = str(claim.get("candidate_claim_source_type_cn") or "").strip()
    if source == "本品已成立卖点":
        return "竞品已成立卖点"
    return source


def _claim_market_signal_text(claim: dict[str, Any]) -> str:
    existing = str(claim.get("candidate_market_signal_cn") or "").strip()
    if existing:
        return existing
    role = str(claim.get("candidate_role") or "").strip()
    if role == "premium_driver_estimated":
        return "市场观测：溢价相关"
    if role == "sales_driver_estimated":
        return "市场观测：销量相关"
    if role == "basic_threshold":
        return "市场观测：基础门槛"
    label = str(claim.get("candidate_business_value_label") or claim.get("candidate_business_claim_type_cn") or "").strip()
    if "样本" in label:
        return "市场观测：样本不足"
    if "溢价" in label:
        return "市场观测：溢价相关"
    if "销量" in label or "份额" in label:
        return "市场观测：销量相关"
    if "基础" in label or "门槛" in label:
        return "市场观测：基础门槛"
    if "客户" in label:
        return "市场观测：客户价值相关"
    if "待激活" in label:
        return "市场观测：待激活"
    if "厂家" in label:
        return "市场观测：厂家主张"
    return f"市场观测：{label}" if label else ""


def _claim_parameter_level_text(claim: dict[str, Any]) -> str:
    existing = str(claim.get("candidate_parameter_level_cn") or "").strip()
    if existing:
        return existing
    parameter = claim.get("candidate_parameter_competitiveness") or {}
    level_cn = str(parameter.get("overall_parameter_competitiveness_level_cn") or "").strip()
    if level_cn:
        return f"参数口径：{level_cn}"
    downgrade = str(parameter.get("downgrade_reason_cn") or "").strip()
    if "基础门槛" in downgrade:
        return "参数口径：基础门槛"
    if "样本" in downgrade:
        return "参数口径：样本不足"
    return "参数口径：样本不足"


def _claim_parameter_downgrade_text(claim: dict[str, Any]) -> str:
    parameter = claim.get("candidate_parameter_competitiveness") or {}
    downgrade = str(parameter.get("downgrade_reason_cn") or "").strip("。")
    return f"限制：{downgrade}" if downgrade else ""


def _claim_effect_text(claim: dict[str, Any]) -> str:
    pool_effect = claim.get("candidate_pool_effect") or {}
    weekly_delta = _decimal(pool_effect.get("pool_claim_weekly_sales_delta_abs"))
    price_delta = _decimal(pool_effect.get("pool_claim_price_delta_abs"))
    if weekly_delta is not None and weekly_delta > 0:
        return f"池内有该卖点 SKU 周销量约高{_volume_text(weekly_delta)}台"
    if price_delta is not None and price_delta > 0:
        return f"池内有该卖点 SKU 均价约高{_yuan_text(price_delta)}"
    if price_delta is not None and price_delta < 0:
        return f"池内有该卖点 SKU 均价约低{_yuan_text(abs(price_delta))}"
    return ""


def _claim_evidence_text(claim: dict[str, Any]) -> str:
    evidence = claim.get("candidate_evidence_strength") or {}
    parts = []
    for key, label in (("claim", "卖点"), ("param", "参数"), ("comment", "评论")):
        value = _decimal(evidence.get(key))
        if value is not None and value >= Decimal("0.80"):
            parts.append(f"{label}证据强")
    return "、".join(parts[:3])


def _positive_claim_count(claim_value_summary: dict[str, Any]) -> int:
    return sum(len(claim_value_summary.get(key) or []) for key in ("premium_claims", "share_conversion_claims", "customer_value_claims"))


def _price_value_root_cause(*, positive_claim_count: int, low_price_competitors: list[dict[str, Any]]) -> str:
    if low_price_competitors and positive_claim_count == 0:
        return "目标 SKU 的有效价格处在高位，但当前证据没有给出可对抗低价竞品的支付理由；用户看到的是“更贵但不更确定值得”。"
    if low_price_competitors:
        return "目标 SKU 的高价格需要由可感知价值承接，但低价竞品仍在重叠周拿走需求，说明现有价值证明没有覆盖价差。"
    if positive_claim_count == 0:
        return "价格位置缺少稳定卖点和用户任务承接，问题不是价格数字本身，而是用户没有看到价格对应的确定收益。"
    return "价格和销量承接不匹配，现有价值证据还不足以证明当前价格带可以被目标用户接受。"


def _customer_wtp_root_cause(*, positive_count: int, established_count: int) -> str:
    if positive_count == 0 and established_count == 0:
        return "具体原因是购买任务没有被证据化：既没有稳定成立的主战场，也没有可验证的溢价、份额或客户价值卖点，用户无法把价格映射到一个确定收益。"
    if positive_count == 0:
        return "具体原因是缺少可验证的支付理由：即使存在场景机会，当前也没有足够卖点证明用户为什么要为这款买单。"
    if established_count == 0:
        return "具体原因是卖点没有落到稳定购买场景：有一些正向卖点，但还没有被主战场和主任务证明可以持续转化。"
    return "具体原因是支付理由还不够强：已有卖点和战场没有形成足以对抗竞品和价格压力的确定收益。"


def _default_reason_decision(action_keys: list[str]) -> str:
    if "price_band_test" in action_keys:
        return "先做有效价格或权益包测试，再决定是否调整价格带。"
    if "competitor_comparison_message" in action_keys:
        return "先明确对标竞品和防守理由，再决定是否改卖点、权益或定位。"
    if "reframe_primary_scene" in action_keys:
        return "先收敛主战场和主用户任务，再重排卖点表达。"
    return "先补齐证据并做小范围验证，再决定是否扩大动作。"


def _market_position_detail_points(target_summary: dict[str, Any]) -> list[str]:
    market_position = target_summary.get("market_position") or {}
    market_metrics = target_summary.get("market_metrics") or {}
    price_pct = _decimal(market_position.get("price_percentile_in_size"))
    volume_pct = _decimal(market_position.get("volume_percentile_in_size"))
    points: list[str] = []
    if price_pct is not None and volume_pct is not None:
        price_text = _percent_text(price_pct)
        volume_text = _percent_text(volume_pct)
        if price_pct >= Decimal("0.75") and volume_pct <= Decimal("0.30"):
            points.append(f"同尺寸池内价格分位约{price_text}，但销量分位只有{volume_text}，说明价格拿走的价值高于市场成交承接。")
        else:
            points.append(f"同尺寸池内价格分位约{price_text}，销量分位约{volume_text}，价格和销量承接需要一起看。")
    price = _decimal(market_metrics.get("price_wavg"))
    avg_weekly = _decimal(market_metrics.get("avg_weekly_sales_volume"))
    pool_count = market_position.get("same_pool_sku_count")
    if price is not None and avg_weekly is not None and pool_count:
        points.append(f"当前均价约{_yuan_text(price)}、周均销量约{_volume_text(avg_weekly)}台，同池可比 SKU 约{pool_count}个。")
    return points


def _competitor_price_pressure_points(rows: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    for row in rows:
        name = str(row.get("candidate_name") or row.get("candidate_sku_code") or "重点竞品")
        relation = str(row.get("price_relation_cn") or "").strip("。")
        relation = relation.replace("竞品", name, 1) if relation else f"{name}价格更低"
        sales_ratio = _ratio_text(row.get("sales_ratio"))
        amount_ratio = _ratio_text(row.get("amount_ratio"))
        metrics = "，".join(part for part in (f"销量约为其{sales_ratio}" if sales_ratio else "", f"销额约为其{amount_ratio}" if amount_ratio else "") if part)
        suffix = f"，但目标{metrics}" if metrics else ""
        points.append(f"{relation}{suffix}。")
    return points


def _competitor_intercept_points(all_competitors: list[dict[str, Any]], weak_competitors: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    if all_competitors:
        points.append(f"{len(all_competitors)}个重点竞品里有{len(weak_competitors)}个在重叠在售周的销量和销额强于目标，替代压力不是单点偶然。")
    for row in weak_competitors[:3]:
        name = str(row.get("candidate_name") or row.get("candidate_sku_code") or "重点竞品")
        overlap = row.get("overlap_week_count")
        target_avg = _volume_text(row.get("target_avg_weekly_sales_volume"))
        candidate_avg = _volume_text(row.get("candidate_avg_weekly_sales_volume"))
        sales_ratio = _ratio_text(row.get("sales_ratio"))
        amount_ratio = _ratio_text(row.get("amount_ratio"))
        parts = []
        if overlap and target_avg and candidate_avg:
            parts.append(f"{overlap}个重叠周内目标周均{target_avg}台，{name}周均{candidate_avg}台")
        if sales_ratio:
            parts.append(f"销量约为对方{sales_ratio}")
        if amount_ratio:
            parts.append(f"销额约为对方{amount_ratio}")
        if parts:
            points.append(f"对比{name}，{'，'.join(parts)}。")
    return points


def _same_brand_cannibalization_points(rows: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    for row in rows[:3]:
        name = _display_sku_name(row) or str(row.get("sku_code") or "同品牌低价 SKU")
        price_relation = str(row.get("price_relation_cn") or "").strip("。")
        sales_ratio = _ratio_text(row.get("sales_ratio_to_target"))
        avg = _volume_text(row.get("avg_weekly_sales_volume"))
        target_avg = _volume_text(row.get("target_avg_weekly_sales_volume"))
        parts = [price_relation] if price_relation else []
        if avg and target_avg:
            parts.append(f"周均销量约{avg}台，目标周均约{target_avg}台")
        if sales_ratio:
            parts.append(f"周均销量约为目标的{sales_ratio}")
        points.append(f"{name}：{'，'.join(parts)}。")
    return points


def _same_brand_cannibalization_root_cause(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "未发现同品牌低价高销量 SKU 分流信号。"
    top_names = "、".join(_display_sku_name(row) or str(row.get("sku_code") or "") for row in rows[:2])
    return f"具体原因是用户如果想买同品牌，同尺寸池里还有 {top_names} 等更便宜且销量更强的选择；本品若不能讲清楚价差对应的收益，就会被自家产品线分流。"


def _claim_detail_points(rows: list[dict[str, Any]], *, prefix: str) -> list[str]:
    if not rows:
        return []
    names = _claim_names_joined(rows[:4])
    if not names:
        return []
    summaries = [str(row.get("summary_cn") or "").strip("。") for row in rows[:2] if str(row.get("summary_cn") or "").strip()]
    if summaries:
        return [f"{prefix}包括{names}，{'；'.join(summaries)}。"]
    return [f"{prefix}包括{names}。"]


def _dimension_detail_points(rows: list[dict[str, Any]], *, prefix: str) -> list[str]:
    names = [str(row.get("dimension_name") or row.get("dimension_code") or "").strip() for row in rows if isinstance(row, dict)]
    names = [name for name in names if name]
    return [f"{prefix}集中在{'、'.join(names[:4])}，说明当前主价值表达还没有完全站稳。"] if names else []


def _signal_detail_points(rows: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    for row in rows:
        message = str(row.get("message_cn") or row.get("reason_cn") or row.get("gap_code") or "").strip("。")
        if message:
            points.append(f"{message}。")
    return points


def _claim_names_joined(rows: list[dict[str, Any]]) -> str:
    names = [str(row.get("claim_name") or row.get("claim_code") or "").strip() for row in rows if isinstance(row, dict)]
    return "、".join(name for name in names if name) or "相关卖点"


def _ratio_text(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{number.quantize(Decimal('0.01'))}倍"


def _percent_text(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{(number * Decimal('100')).quantize(Decimal('0.1'))}%"


def _yuan_text(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{number.quantize(Decimal('1'))}元"


def _volume_text(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    if number == number.to_integral_value():
        return str(number.quantize(Decimal("1")))
    return str(number.quantize(Decimal("0.1")))


def _signal_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": row.get("signal_type") or "gap_signal", "summary_cn": row.get("message_cn") or row.get("gap_code")} for row in rows]


def _claim_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": "claim_value", "summary_cn": row.get("claim_name") or row.get("claim_code")} for row in rows]


def _dimension_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": "semantic_dimension", "summary_cn": row.get("dimension_name") or row.get("dimension_code")} for row in rows]


def _competitor_price_summary(candidate: dict[str, Any]) -> str:
    price_gap_pct = _decimal(candidate.get("price_gap_pct_to_target"))
    price_gap = _decimal(candidate.get("price_gap_to_target"))
    if price_gap is None:
        return ""
    if price_gap < 0:
        return f"竞品价格更低，价差约{_yuan_text(abs(price_gap))}。"
    if price_gap > 0:
        return f"竞品价格更高，价差约{_yuan_text(price_gap)}。"
    if price_gap_pct is not None:
        return f"竞品价格接近，差异约{_percent_text(price_gap_pct)}。"
    return "竞品价格接近。"


def _semantic_overlap_summary(overlap: dict[str, Any]) -> str:
    matched: list[str] = []
    for section in ("value_battlefield", "user_task", "target_group"):
        matched.extend(str(code) for code in ((overlap.get(section) or {}).get("matched_codes") or [])[:3])
    return f"语义重合点：{'、'.join(matched)}。" if matched else ""


def _display_sku_name(sku: dict[str, Any]) -> str:
    return " ".join(str(part) for part in (sku.get("brand_name"), sku.get("model_name") or sku.get("sku_code")) if part)


def _float_or_none(value: Any) -> float | None:
    number = _decimal(value)
    return float(number) if number is not None else None


def _safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator in (None, Decimal("0")):
        return None
    return numerator / denominator


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
