"""Atomic analyst handlers."""

from __future__ import annotations

from typing import Any

from app.services.core3_real_data.analyst.analyst_repository import AnalystRepository, unique_skus
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext, AnalystStatus, base_result


class AtomicAnalystHandlers:
    def __init__(self, repository: AnalystRepository) -> None:
        self.repository = repository

    def resolve_sku(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        candidates = unique_skus(
            self.repository.resolve_sku(
                batch_id=context.batch_id,
                product_category=context.product_category,
                market_window=context.market_window,
                query=query,
                sku_code=sku_code,
                model_name=model_name,
                limit=limit,
            )
        )
        if not candidates:
            return base_result(
                status=AnalystStatus.NOT_FOUND,
                command="resolve-sku",
                context=context,
                result={"candidates": []},
                limitations=["当前批次未找到匹配 SKU。"],
                message_cn="没有找到匹配的 SKU，请提供更完整型号或 SKU code。",
            )
        if len(candidates) > 1:
            return base_result(
                status=AnalystStatus.AMBIGUOUS,
                command="resolve-sku",
                context=context,
                result={"candidates": [candidate.to_dict() for candidate in candidates]},
                limitations=["自然语言或型号匹配到多个 SKU，需要用户确认。"],
                message_cn="匹配到多个 SKU，请指定 SKU code。",
            )
        candidate = candidates[0]
        return base_result(
            status=AnalystStatus.OK,
            command="resolve-sku",
            context=context,
            target=candidate.to_dict(),
            result={"resolved_sku": candidate.to_dict(), "candidates": [candidate.to_dict()]},
            atoms_used=[{"ability_code": "resolve-sku", "status": "ok"}],
            evidence=[{"source_module": candidate.source, "sku_code": candidate.sku_code}],
            answer_outline=[f"已解析到 {candidate.brand_name or ''} {candidate.model_name or candidate.sku_code}。".strip()],
        )

    def sku_fact_brief(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        resolved = self._resolve_one(context, command="sku-fact-brief", query=query, sku_code=sku_code, model_name=model_name)
        if resolved["status"] != AnalystStatus.OK:
            return resolved["payload"]
        candidate = resolved["candidate"]
        fact_brief = self.repository.sku_fact_brief(
            batch_id=context.batch_id,
            sku=candidate,
            product_category=context.product_category,
            market_window=context.market_window,
            analysis_population=context.analysis_population,
            allocation_limit=limit,
        )
        missing_sections = fact_brief["missing_sections"]
        outline = [
            f"已汇总 {candidate.brand_name or ''} {candidate.model_name or candidate.sku_code} 的基础事实画像。".strip(),
        ]
        if missing_sections:
            outline.append(f"缺少或未生成的事实层：{', '.join(missing_sections)}。")
        return base_result(
            status=AnalystStatus.OK,
            command="sku-fact-brief",
            context=context,
            target=candidate.to_dict(),
            result={"fact_brief": fact_brief},
            atoms_used=[
                {"ability_code": "resolve-sku", "status": "ok"},
                {"ability_code": "sku-fact-brief", "status": "ok"},
            ],
            evidence=fact_brief["evidence_sources"],
            limitations=[f"缺少或未生成的事实层：{', '.join(missing_sections)}。"] if missing_sections else [],
            answer_outline=outline,
        )

    def semantic_dimension_space(
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
    ) -> dict[str, Any]:
        if context.product_category != "TV":
            return base_result(
                status=AnalystStatus.UNSUPPORTED,
                command="semantic-dimension-space",
                context=context,
                limitations=["当前只有 TV 品类已生成 M11D 语义市场图谱。"],
                message_cn="当前品类尚未支持语义市场空间查询。",
            )
        items = self.repository.semantic_dimension_space(
            batch_id=context.batch_id,
            product_category=context.product_category,
            analysis_population=context.analysis_population,
            market_window=context.market_window,
            dimension_type=dimension_type,
            dimension_code=dimension_code,
            query=query,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band=price_band,
            limit=limit,
        )
        if not items:
            return base_result(
                status=AnalystStatus.NOT_FOUND,
                command="semantic-dimension-space",
                context=context,
                result={
                    "dimension_type": dimension_type,
                    "dimension_code": dimension_code,
                    "query": query,
                    "items": [],
                },
                limitations=["没有找到匹配的 M11D 图谱空间。"],
                message_cn="没有找到匹配的语义市场空间，请检查维度类型、维度 code 或先执行 M11D。",
            )
        return base_result(
            status=AnalystStatus.OK,
            command="semantic-dimension-space",
            context=context,
            result={
                "dimension_type": dimension_type or "all",
                "dimension_code": dimension_code,
                "query": query,
                "filters": {
                    "brand_name": brand_name,
                    "size_tier": size_tier,
                    "price_band": price_band,
                    "limit": limit,
                },
                "summary_count": len(items),
                "items": items,
            },
            atoms_used=[{"ability_code": "semantic-dimension-space", "status": "ok"}],
            evidence=[{"source_module": "M11D", "row_count": len(items)}],
            answer_outline=[f"已返回 {len(items)} 个语义市场空间及其 SKU 贡献。"],
        )

    def same_size_price_candidates(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        resolved = self._resolve_one(context, command="same-size-price-candidates", query=query, sku_code=sku_code, model_name=model_name)
        if resolved["status"] != AnalystStatus.OK:
            return resolved["payload"]
        candidate = resolved["candidate"]
        candidate_search = self.repository.same_size_price_candidates(
            batch_id=context.batch_id,
            target_sku_code=candidate.sku_code,
            product_category=context.product_category,
            market_window=context.market_window,
            limit=limit,
        )
        limitations = []
        if not candidate_search.get("target_market"):
            limitations.append("目标 SKU 缺少 M07 市场画像，无法按同尺寸价格池生成候选。")
        if not candidate_search.get("candidates"):
            limitations.append("当前同尺寸、同价格带市场池没有找到其他候选 SKU。")
        return base_result(
            status=AnalystStatus.OK,
            command="same-size-price-candidates",
            context=context,
            target=candidate.to_dict(),
            result={"candidate_search": candidate_search},
            atoms_used=[
                {"ability_code": "resolve-sku", "status": "ok"},
                {"ability_code": "same-size-price-candidates", "status": "ok"},
            ],
            evidence=[{"source_module": "M07", "row_count": 1 + len(candidate_search.get("candidates") or [])}],
            limitations=limitations,
            answer_outline=[f"已按同尺寸、同价格带返回 {len(candidate_search.get('candidates') or [])} 个候选竞品。"],
        )

    def semantic_overlap(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        candidate_sku_code: str | None = None,
    ) -> dict[str, Any]:
        pair = self._resolve_pair(
            context,
            command="semantic-overlap",
            query=query,
            sku_code=sku_code,
            model_name=model_name,
            candidate_sku_code=candidate_sku_code,
        )
        if pair["status"] != AnalystStatus.OK:
            return pair["payload"]
        target = pair["target"]
        candidate = pair["candidate"]
        overlap = self.repository.semantic_overlap(
            batch_id=context.batch_id,
            product_category=context.product_category,
            target_sku_code=target.sku_code,
            candidate_sku_code=candidate.sku_code,
        )
        return base_result(
            status=AnalystStatus.OK,
            command="semantic-overlap",
            context=context,
            target=target.to_dict(),
            result={"candidate": candidate.to_dict(), "semantic_overlap": overlap},
            atoms_used=[
                {"ability_code": "resolve-sku", "status": "ok"},
                {"ability_code": "semantic-overlap", "status": "ok"},
            ],
            evidence=[{"source_module": module, "row_count": 2} for module in overlap["source_modules"]],
            answer_outline=[f"已计算 {target.sku_code} 与 {candidate.sku_code} 的任务、客群、战场语义重合。"],
        )

    def sales_overlap(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        candidate_sku_code: str | None = None,
    ) -> dict[str, Any]:
        pair = self._resolve_pair(
            context,
            command="sales-overlap",
            query=query,
            sku_code=sku_code,
            model_name=model_name,
            candidate_sku_code=candidate_sku_code,
        )
        if pair["status"] != AnalystStatus.OK:
            return pair["payload"]
        target = pair["target"]
        candidate = pair["candidate"]
        overlap = self.repository.sales_overlap(
            batch_id=context.batch_id,
            target_sku_code=target.sku_code,
            candidate_sku_code=candidate.sku_code,
            market_window=context.market_window,
        )
        limitations = []
        if overlap.get("method") == "market_profile_active_week_average_fallback":
            limitations.append("未找到两款 SKU 的 M01 周度明细重叠，当前为 M07 活跃周均回退结果。")
        return base_result(
            status=AnalystStatus.OK,
            command="sales-overlap",
            context=context,
            target=target.to_dict(),
            result={"candidate": candidate.to_dict(), "sales_overlap": overlap},
            atoms_used=[
                {"ability_code": "resolve-sku", "status": "ok"},
                {"ability_code": "sales-overlap", "status": "ok"},
            ],
            evidence=[{"source_module": "M01", "row_count": overlap.get("overlap_week_count", 0)}, {"source_module": "M07", "row_count": 2}],
            limitations=limitations,
            answer_outline=[f"已按重叠在售周计算 {target.sku_code} 与 {candidate.sku_code} 的周均销量/销额。"],
        )

    def param_claim_overlap(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        candidate_sku_code: str | None = None,
    ) -> dict[str, Any]:
        pair = self._resolve_pair(
            context,
            command="param-claim-overlap",
            query=query,
            sku_code=sku_code,
            model_name=model_name,
            candidate_sku_code=candidate_sku_code,
        )
        if pair["status"] != AnalystStatus.OK:
            return pair["payload"]
        target = pair["target"]
        candidate = pair["candidate"]
        overlap = self.repository.param_claim_overlap(
            batch_id=context.batch_id,
            product_category=context.product_category,
            target_sku_code=target.sku_code,
            candidate_sku_code=candidate.sku_code,
        )
        return base_result(
            status=AnalystStatus.OK,
            command="param-claim-overlap",
            context=context,
            target=target.to_dict(),
            result={"candidate": candidate.to_dict(), "param_claim_overlap": overlap},
            atoms_used=[
                {"ability_code": "resolve-sku", "status": "ok"},
                {"ability_code": "param-claim-overlap", "status": "ok"},
            ],
            evidence=[{"source_module": module, "row_count": 2} for module in overlap["source_modules"]],
            answer_outline=[f"已计算 {target.sku_code} 与 {candidate.sku_code} 的参数、卖点和卖点位置重合。"],
        )

    def comment_support(
        self,
        context: AnalystContext,
        *,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        claim_code: str | None = None,
        param_code: str | None = None,
        user_task_code: str | None = None,
        target_group_code: str | None = None,
        battlefield_code: str | None = None,
    ) -> dict[str, Any]:
        resolved = self._resolve_one(context, command="comment-support", query=query, sku_code=sku_code, model_name=model_name)
        if resolved["status"] != AnalystStatus.OK:
            return resolved["payload"]
        candidate = resolved["candidate"]
        support = self.repository.comment_support(
            batch_id=context.batch_id,
            product_category=context.product_category,
            sku_code=candidate.sku_code,
            claim_code=claim_code,
            param_code=param_code,
            user_task_code=user_task_code,
            target_group_code=target_group_code,
            battlefield_code=battlefield_code,
        )
        limitations = [] if support.get("comment_profile") else ["目标 SKU 缺少 M05C 评论事实画像。"]
        return base_result(
            status=AnalystStatus.OK,
            command="comment-support",
            context=context,
            target=candidate.to_dict(),
            result={"comment_support": support},
            atoms_used=[
                {"ability_code": "resolve-sku", "status": "ok"},
                {"ability_code": "comment-support", "status": "ok"},
            ],
            evidence=[{"source_module": "M05C", "row_count": 1}, {"source_module": "M09C/M10C/M11C", "row_count": 3}],
            limitations=limitations,
            answer_outline=[f"已查询 {candidate.sku_code} 的评论对参数、卖点或语义维度的支撑。"],
        )

    def planned_atom(self, context: AnalystContext, *, command: str, **_: Any) -> dict[str, Any]:
        return base_result(
            status=AnalystStatus.NOT_IMPLEMENTED,
            command=command,
            context=context,
            atoms_used=[{"ability_code": command, "status": "planned"}],
            limitations=["该原子分析能力的 CLI 框架已创建，业务算法将在后续步骤实现。"],
            message_cn=f"{command} 原子分析能力尚未实现。",
        )

    def _resolve_one(
        self,
        context: AnalystContext,
        *,
        command: str = "resolve-sku",
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        candidates = unique_skus(
            self.repository.resolve_sku(
                batch_id=context.batch_id,
                product_category=context.product_category,
                market_window=context.market_window,
                query=query,
                sku_code=sku_code,
                model_name=model_name,
                limit=10,
            )
        )
        if not candidates:
            return {
                "status": AnalystStatus.NOT_FOUND,
                "payload": base_result(
                    status=AnalystStatus.NOT_FOUND,
                    command=command,
                    context=context,
                    result={"candidates": []},
                    limitations=["当前批次未找到匹配 SKU。"],
                    message_cn="没有找到匹配的 SKU，请提供更完整型号或 SKU code。",
                ),
            }
        if len(candidates) > 1:
            return {
                "status": AnalystStatus.AMBIGUOUS,
                "payload": base_result(
                    status=AnalystStatus.AMBIGUOUS,
                    command=command,
                    context=context,
                    result={"candidates": [candidate.to_dict() for candidate in candidates]},
                    limitations=["自然语言或型号匹配到多个 SKU，需要用户确认。"],
                    message_cn="匹配到多个 SKU，请指定 SKU code。",
                ),
            }
        return {"status": AnalystStatus.OK, "candidate": candidates[0]}

    def _resolve_pair(
        self,
        context: AnalystContext,
        *,
        command: str,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        candidate_sku_code: str | None = None,
    ) -> dict[str, Any]:
        target_resolved = self._resolve_one(context, command=command, query=query, sku_code=sku_code, model_name=model_name)
        if target_resolved["status"] != AnalystStatus.OK:
            return target_resolved
        if not candidate_sku_code:
            return {
                "status": AnalystStatus.ERROR,
                "payload": base_result(
                    status=AnalystStatus.ERROR,
                    command=command,
                    context=context,
                    limitations=["该命令需要 candidate_sku_code。"],
                    message_cn="请提供候选 SKU code，例如 --candidate-sku-code TV00030001。",
                ),
            }
        candidate_resolved = self._resolve_one(context, command=command, sku_code=candidate_sku_code)
        if candidate_resolved["status"] != AnalystStatus.OK:
            return candidate_resolved
        target = target_resolved["candidate"]
        candidate = candidate_resolved["candidate"]
        if target.sku_code == candidate.sku_code:
            return {
                "status": AnalystStatus.ERROR,
                "payload": base_result(
                    status=AnalystStatus.ERROR,
                    command=command,
                    context=context,
                    target=target.to_dict(),
                    limitations=["目标 SKU 和候选 SKU 不能相同。"],
                    message_cn="目标 SKU 和候选 SKU 相同，无法做竞品对比。",
                ),
            }
        return {"status": AnalystStatus.OK, "target": target, "candidate": candidate}
