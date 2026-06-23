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
        for rank, row in enumerate(candidate_rows, start=1):
            candidate_sku = row.get("sku_code")
            if not candidate_sku:
                continue
            semantic = self.atomic_handlers.semantic_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku)
            param_claim = self.atomic_handlers.param_claim_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku)
            sales = self.atomic_handlers.sales_overlap(context, sku_code=target_sku, candidate_sku_code=candidate_sku)
            pair_atom_results.extend([semantic, param_claim, sales])
            competitors.append(_competitor_item(rank, row, semantic, param_claim, sales))
        atom_results = [target, fact, candidates_result, *pair_atom_results]
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
                "candidate_count": len(competitors),
                "candidates": competitors,
            }
        }
        if answer_style == "xiaoao" or with_report != "none":
            result_payload["competitor_answer"] = build_competitor_answer(
                target=target["target"],
                target_fact_brief=target_fact_brief,
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
        comment = self.atomic_handlers.comment_support(context, sku_code=target_sku)
        gaps = self.atomic_handlers.opportunity_gaps(context, sku_code=target_sku, limit=limit)
        primary_battlefield_code = _primary_battlefield_code(fact)
        primary_space = (
            self.atomic_handlers.semantic_dimension_space(context, dimension_type="battlefield", dimension_code=primary_battlefield_code, limit=limit)
            if primary_battlefield_code
            else {}
        )
        atom_results = [fact, comment, gaps, primary_space]
        return base_result(
            status=AnalystStatus.OK,
            command="premium-claim-drivers",
            context=context,
            target=fact["target"],
            result={
                "premium_claim_drivers": _premium_claim_driver_payload(fact, comment, gaps, primary_space),
            },
            sop_steps=_steps("premium-claim-drivers", atom_results),
            atoms_used=_atoms_used(atom_results),
            evidence=_evidence(atom_results),
            limitations=_limitations(atom_results),
            answer_outline=["已按事实卖点、评论支撑、主/辅战场和拖后腿信号识别溢价卖点候选、基础卖点和风险卖点。"],
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
    return {
        "premium_driver_claim_codes": sorted((fact_claim_codes & supported_claim_codes) - contradicted_claim_codes),
        "basic_support_claim_codes": sorted(fact_claim_codes - supported_claim_codes - contradicted_claim_codes),
        "brand_claim_only_codes": sorted(unsupported_claim_codes),
        "drag_factor_claim_codes": sorted(contradicted_claim_codes),
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
        "method_note_cn": "当前基于 SKU 级事实卖点、评论支撑和主/辅战场上下文识别溢价卖点候选；逐条卖点到战场贡献的细分映射可在后续增强。",
    }


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
