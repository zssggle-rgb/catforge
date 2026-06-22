"""Service layer for CatForge analyst CLI."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.core3_real_data.analyst.ability_registry import ABILITIES_BY_CODE, get_ability, list_abilities
from app.services.core3_real_data.analyst.analyst_repository import AnalystRepository
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext, AnalystStatus, base_result
from app.services.core3_real_data.analyst.atomic_handlers import AtomicAnalystHandlers
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators


LATEST_BATCH = "latest"

ATOM_COMMANDS = {
    "resolve-sku",
    "sku-fact-brief",
    "same-size-price-candidates",
    "semantic-overlap",
    "sales-overlap",
    "param-claim-overlap",
    "comment-support",
    "semantic-dimension-space",
    "opportunity-gaps",
}

SOP_COMMANDS = {
    "competitor-set",
    "why-sales-diff",
    "premium-claim-drivers",
    "battlefield-space",
    "battlefield-opportunity",
    "sku-business-brief",
}


class CatForgeAnalystService:
    def __init__(self, db: Session, *, project_id: str, category_code: str) -> None:
        self.repository = AnalystRepository(db, project_id=project_id, category_code=category_code)
        self.atomic_handlers = AtomicAnalystHandlers(self.repository)
        self.sop_orchestrators = SopOrchestrators()
        self.project_id = project_id
        self.category_code = category_code

    def build_context(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str,
        analysis_population: str,
        resolve_latest: bool = True,
    ) -> AnalystContext:
        resolved_batch_id = self.resolve_batch_id(batch_id) if resolve_latest else batch_id
        return AnalystContext(
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=resolved_batch_id,
            product_category=normalize_product_category(product_category),
            market_window=market_window,
            analysis_population=analysis_population,
        )

    def resolve_batch_id(self, batch_id: str) -> str:
        if batch_id != LATEST_BATCH:
            return batch_id
        latest = self.repository.latest_batch_id()
        if not latest:
            raise CatForgeAnalystError(f"没有找到项目 {self.project_id} / {self.category_code} 的可用批次。")
        return latest

    def list_abilities(self, context: AnalystContext, *, ability_type: str | None = None) -> dict[str, Any]:
        normalized_type = ability_type if ability_type in {None, "atom", "sop", "router"} else None
        return base_result(
            status=AnalystStatus.OK,
            command="list-abilities",
            context=context,
            result={"abilities": list_abilities(ability_type=normalized_type)},  # type: ignore[arg-type]
        )

    def dispatch(self, command: str, context: AnalystContext, **kwargs: Any) -> dict[str, Any]:
        if command == "resolve-sku":
            return self.atomic_handlers.resolve_sku(context, **kwargs)
        if command == "sku-fact-brief":
            return self.atomic_handlers.sku_fact_brief(context, **kwargs)
        if command == "same-size-price-candidates":
            return self.atomic_handlers.same_size_price_candidates(context, **kwargs)
        if command == "semantic-overlap":
            return self.atomic_handlers.semantic_overlap(context, **kwargs)
        if command == "sales-overlap":
            return self.atomic_handlers.sales_overlap(context, **kwargs)
        if command == "param-claim-overlap":
            return self.atomic_handlers.param_claim_overlap(context, **kwargs)
        if command == "comment-support":
            return self.atomic_handlers.comment_support(context, **kwargs)
        if command == "semantic-dimension-space":
            return self.atomic_handlers.semantic_dimension_space(context, **kwargs)
        if command in ATOM_COMMANDS:
            return self.atomic_handlers.planned_atom(context, command=command, **kwargs)
        if command in SOP_COMMANDS:
            return self.sop_orchestrators.planned_sop(context, command=command, **kwargs)
        if command == "ask":
            question = str(kwargs.pop("question", "") or "")
            return self.ask(context, question=question, **kwargs)
        raise CatForgeAnalystError(f"不支持的 analyst 命令：{command}")

    def ask(self, context: AnalystContext, *, question: str, **kwargs: Any) -> dict[str, Any]:
        routed_command = route_question(question)
        routed_ability = get_ability(routed_command)
        result = self.dispatch(routed_command, context, **kwargs)
        result["routed_command"] = routed_command
        result["routing"] = {
            "question": question,
            "routed_command": routed_command,
            "ability_type": routed_ability.ability_type if routed_ability else None,
            "confidence": "rule_based",
        }
        return result


def route_question(question: str) -> str:
    normalized = question.strip().lower()
    if re.search(r"竞品|竞争|和谁.*比|对手", normalized):
        return "competitor-set"
    if re.search(r"为什么|卖得好|卖得差|比.*好|比.*差", normalized):
        return "why-sales-diff"
    if re.search(r"溢价|卖点|选择理由|用户选择|支撑.*选择", normalized):
        return "premium-claim-drivers"
    if re.search(r"空间|多大|市场.*大小|有哪些 sku|哪些sku|图谱", normalized):
        return "battlefield-space"
    if re.search(r"机会|进入更多|扩大销量|抢", normalized):
        return "battlefield-opportunity"
    if re.search(r"画像|综合|情况|介绍|摘要", normalized):
        return "sku-business-brief"
    return "sku-business-brief"


def normalize_product_category(value: str) -> str:
    normalized = (value or "tv").strip().upper()
    if normalized in {"TV", "彩电", "电视"}:
        return "TV"
    if normalized in {"AC", "空调"}:
        return "AC"
    raise CatForgeAnalystError(f"不支持的产品品类：{value}")


class CatForgeAnalystError(Exception):
    pass
