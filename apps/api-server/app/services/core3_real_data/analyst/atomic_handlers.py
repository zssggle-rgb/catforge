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

    def planned_atom(self, context: AnalystContext, *, command: str, **_: Any) -> dict[str, Any]:
        return base_result(
            status=AnalystStatus.NOT_IMPLEMENTED,
            command=command,
            context=context,
            atoms_used=[{"ability_code": command, "status": "planned"}],
            limitations=["该原子分析能力的 CLI 框架已创建，业务算法将在后续步骤实现。"],
            message_cn=f"{command} 原子分析能力尚未实现。",
        )
