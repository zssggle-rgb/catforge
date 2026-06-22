"""Service layer for CatForge analyst CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
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

SKU_CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:TV|AC)\d{6,}(?![A-Za-z0-9])", re.IGNORECASE)
DIMENSION_CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:BF|TASK|TG)_[A-Z0-9_]+(?![A-Za-z0-9])", re.IGNORECASE)
MODEL_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{2,3}[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+)?|[A-Za-z]{1,8}\d{2,3}[A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+)?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteDecision:
    command: str
    confidence: str
    matched_rule: str
    extracted_params: dict[str, Any]


class CatForgeAnalystService:
    def __init__(self, db: Session, *, project_id: str, category_code: str) -> None:
        self.repository = AnalystRepository(db, project_id=project_id, category_code=category_code)
        self.atomic_handlers = AtomicAnalystHandlers(self.repository)
        self.sop_orchestrators = SopOrchestrators(self.atomic_handlers)
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
        if command == "opportunity-gaps":
            return self.atomic_handlers.opportunity_gaps(context, **kwargs)
        if command == "semantic-dimension-space":
            return self.atomic_handlers.semantic_dimension_space(context, **kwargs)
        if command in ATOM_COMMANDS:
            return self.atomic_handlers.planned_atom(context, command=command, **kwargs)
        if command in SOP_COMMANDS:
            return self.sop_orchestrators.dispatch(command, context, **kwargs)
        if command == "ask":
            question = str(kwargs.pop("question", "") or "")
            return self.ask(context, question=question, **kwargs)
        raise CatForgeAnalystError(f"不支持的 analyst 命令：{command}")

    def ask(self, context: AnalystContext, *, question: str, **kwargs: Any) -> dict[str, Any]:
        route = route_question(question, explicit_params=kwargs)
        routed_command = route.command
        routed_ability = get_ability(routed_command)
        merged_kwargs = merge_route_kwargs(explicit_kwargs=kwargs, extracted_kwargs=route.extracted_params)
        result = self.dispatch(routed_command, context, **merged_kwargs)
        explicit_param_keys = sorted(key for key, value in kwargs.items() if value not in (None, ""))
        applied_param_keys = sorted(set(route.extracted_params) | set(explicit_param_keys))
        applied_params = {
            key: merged_kwargs.get(key)
            for key in applied_param_keys
            if merged_kwargs.get(key) not in (None, "")
        }
        result["routed_command"] = routed_command
        result["routing"] = {
            "question": question,
            "routed_command": routed_command,
            "ability_type": routed_ability.ability_type if routed_ability else None,
            "confidence": route.confidence,
            "matched_rule": route.matched_rule,
            "extracted_params": route.extracted_params,
            "applied_params": applied_params,
            "explicit_param_keys": explicit_param_keys,
        }
        return result


def route_question(question: str, explicit_params: dict[str, Any] | None = None) -> RouteDecision:
    normalized = question.strip().lower()
    extracted_params = extract_question_params(question)
    routing_params = merge_route_kwargs(explicit_kwargs=explicit_params or {}, extracted_kwargs=extracted_params)
    command = "sku-business-brief"
    matched_rule = "fallback_sku_business_brief"
    confidence = "low"

    if re.search(r"评论.*支撑|支撑.*评论", normalized) and _has_any_code_filter(routing_params):
        command = "comment-support"
        matched_rule = "comment_support_code_filter"
        confidence = "high"
    elif re.search(r"为什么|销量差|卖得好|卖得差|比.*好|比.*差", normalized):
        command = "why-sales-diff"
        matched_rule = "sales_difference"
        confidence = "high" if routing_params.get("candidate_sku_code") else "medium"
    elif re.search(r"竞品|竞争|和谁.*比|和谁竞争|对手|比较对象", normalized):
        command = "competitor-set"
        matched_rule = "competitor_set"
        confidence = "high" if _has_sku_target(routing_params) else "medium"
    elif re.search(r"溢价|卖点|选择理由|用户选择|支撑.*选择|销量.*支撑", normalized):
        command = "premium-claim-drivers"
        matched_rule = "premium_claim_drivers"
        confidence = "high" if _has_sku_target(routing_params) else "medium"
    elif re.search(r"机会|进入更多|扩大销量|抢|短板|缺口", normalized):
        command = "battlefield-opportunity"
        matched_rule = "battlefield_opportunity"
        confidence = "high" if _has_sku_target(routing_params) else "medium"
    elif re.search(r"战场|空间|多大|市场.*大小|有哪些\s*sku|哪些sku|图谱", normalized):
        command = "battlefield-space"
        matched_rule = "battlefield_space"
        confidence = "high" if routing_params.get("dimension_code") or routing_params.get("query") else "medium"
        extracted_params.setdefault("dimension_type", "battlefield")
    elif re.search(r"画像|综合|情况|介绍|摘要|怎么样", normalized):
        command = "sku-business-brief"
        matched_rule = "sku_business_brief"
        confidence = "high" if _has_sku_target(routing_params) else "medium"

    return RouteDecision(command=command, confidence=confidence, matched_rule=matched_rule, extracted_params=extracted_params)


def extract_question_params(question: str) -> dict[str, Any]:
    text = question.strip()
    params: dict[str, Any] = {}
    sku_codes = _extract_sku_codes(text)
    if sku_codes:
        params["sku_code"] = sku_codes[0]
    if len(sku_codes) >= 2:
        params["candidate_sku_code"] = sku_codes[1]

    dimension_code = _extract_dimension_code(text)
    if dimension_code:
        params["dimension_code"] = dimension_code
        params["dimension_type"] = _dimension_type_for_code(dimension_code)
        if dimension_code.startswith("BF_"):
            params["battlefield_code"] = dimension_code
        elif dimension_code.startswith("TASK_"):
            params["user_task_code"] = dimension_code
        elif dimension_code.startswith("TG_"):
            params["target_group_code"] = dimension_code
    elif "战场" in text:
        dimension_query = _extract_battlefield_query(text)
        if dimension_query:
            params["query"] = dimension_query
            params["dimension_type"] = "battlefield"

    if "sku_code" not in params:
        model_token = _extract_model_token(text)
        if model_token:
            params["model_name"] = model_token

    return params


def merge_route_kwargs(*, explicit_kwargs: dict[str, Any], extracted_kwargs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(explicit_kwargs)
    for key, value in extracted_kwargs.items():
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged


def _extract_sku_codes(text: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for match in SKU_CODE_PATTERN.finditer(text):
        code = match.group(0).upper()
        if code in seen:
            continue
        seen.add(code)
        result.append(code)
    return result


def _extract_dimension_code(text: str) -> str | None:
    match = DIMENSION_CODE_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _dimension_type_for_code(code: str) -> str:
    if code.startswith("TASK_"):
        return "user_task"
    if code.startswith("TG_"):
        return "target_group"
    return "battlefield"


def _extract_model_token(text: str) -> str | None:
    for match in MODEL_TOKEN_PATTERN.finditer(text):
        token = " ".join(match.group(0).strip().split())
        if not token or SKU_CODE_PATTERN.fullmatch(token) or DIMENSION_CODE_PATTERN.fullmatch(token):
            continue
        if token.lower() in {"sku", "pro", "max", "mini"}:
            continue
        return token
    return None


def _extract_battlefield_query(text: str) -> str | None:
    cleaned = re.sub(r"(有哪些\s*SKU|有哪些sku|哪些\s*SKU|哪些sku|市场空间|空间|图谱|多大|多少|包括哪些|包括|里面|里|中|的|？|\?)", "", text, flags=re.IGNORECASE)
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_+-]{2,}战场", cleaned)
    return candidates[-1] if candidates else None


def _has_sku_target(params: dict[str, Any]) -> bool:
    return bool(params.get("sku_code") or params.get("model_name") or params.get("query"))


def _has_any_code_filter(params: dict[str, Any]) -> bool:
    return any(params.get(key) for key in ("claim_code", "param_code", "user_task_code", "target_group_code", "battlefield_code"))


def normalize_product_category(value: str) -> str:
    normalized = (value or "tv").strip().upper()
    if normalized in {"TV", "彩电", "电视"}:
        return "TV"
    if normalized in {"AC", "空调"}:
        return "AC"
    raise CatForgeAnalystError(f"不支持的产品品类：{value}")


class CatForgeAnalystError(Exception):
    pass
