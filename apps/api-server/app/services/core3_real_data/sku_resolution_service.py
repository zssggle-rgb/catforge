"""SKU resolution for Core3 business APIs."""

from __future__ import annotations

from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.api_response_mapper import target_profile_from_sku
from app.services.core3_real_data.api_response_schemas import ApiQueryError, Core3V2SkuResolveResponse


class SkuResolutionService:
    def __init__(self, repository: Core3RealDataApiRepository) -> None:
        self.repository = repository

    def resolve(self, query: str) -> Core3V2SkuResolveResponse:
        normalized = query.strip()
        if not normalized:
            raise ApiQueryError(
                status_code=400,
                error_code="empty_sku_query",
                message_cn="请输入 SKU 编号或型号名称。",
            )
        batch = self.repository.latest_batch()
        matches = self.repository.find_sku_matches(normalized, batch.batch_id if batch else None)
        candidates = [target_profile_from_sku(item) for item in matches]
        exact = [
            item
            for item in candidates
            if item.sku_code == normalized or (item.model_name or "").lower() == normalized.lower()
        ]
        if len(exact) == 1:
            return Core3V2SkuResolveResponse(
                status="unique",
                query=normalized,
                target=exact[0],
                candidates=candidates,
                message_cn=f"已匹配到 {exact[0].display_name_cn}。",
            )
        if len(candidates) == 1:
            return Core3V2SkuResolveResponse(
                status="unique",
                query=normalized,
                target=candidates[0],
                candidates=candidates,
                message_cn=f"已匹配到 {candidates[0].display_name_cn}。",
            )
        if not candidates:
            raise ApiQueryError(
                status_code=404,
                error_code="sku_not_found",
                message_cn=f"没有找到与“{normalized}”匹配的 SKU。",
                action_hint_cn="请确认该 SKU 已完成 M01 清洗，或换用商品编号查询。",
            )
        return Core3V2SkuResolveResponse(
            status="ambiguous",
            query=normalized,
            candidates=candidates,
            message_cn=f"找到 {len(candidates)} 个候选 SKU，需要选择一个目标商品。",
            action_hint_cn="请在候选列表中选择具体 SKU 后再打开竞品报告。",
        )

    def resolve_unique_sku_code(self, query: str) -> str:
        result = self.resolve(query)
        if result.target is None:
            raise ApiQueryError(
                status_code=409,
                error_code="sku_query_ambiguous",
                message_cn=result.message_cn,
                action_hint_cn=result.action_hint_cn,
            )
        return result.target.sku_code
