"""Shared schemas for CatForge analyst commands."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class AnalystStatus(str, Enum):
    OK = "ok"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    NOT_IMPLEMENTED = "not_implemented"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True)
class AnalystContext:
    project_id: str
    category_code: str
    batch_id: str
    product_category: str
    market_window: str = "full_observed_window"
    analysis_population: str = "fact_complete_with_comment"


@dataclass(frozen=True)
class ResolvedSku:
    sku_code: str
    brand_name: str | None
    model_name: str | None
    product_category: str
    size_tier: str | None = None
    price_band_in_size_tier: str | None = None
    screen_size_inch: Decimal | None = None
    weighted_price: Decimal | None = None
    avg_weekly_sales_volume: Decimal | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sku_code": self.sku_code,
            "brand_name": self.brand_name,
            "model_name": self.model_name,
            "product_category": self.product_category,
            "size_tier": self.size_tier,
            "price_band_in_size_tier": self.price_band_in_size_tier,
            "screen_size_inch": self.screen_size_inch,
            "weighted_price": self.weighted_price,
            "avg_weekly_sales_volume": self.avg_weekly_sales_volume,
            "source": self.source,
        }


def base_result(
    *,
    status: AnalystStatus,
    command: str,
    context: AnalystContext,
    question_type: str | None = None,
    target: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    sop_steps: list[dict[str, Any]] | None = None,
    atoms_used: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    answer_outline: list[str] | None = None,
    message_cn: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status.value,
        "command": command,
        "question_type": question_type or command.replace("-", "_"),
        "project_id": context.project_id,
        "category_code": context.category_code,
        "product_category": context.product_category,
        "batch_id": context.batch_id,
        "analysis_population": context.analysis_population,
        "market_window": context.market_window,
        "target": target or {},
        "sop_steps": sop_steps or [],
        "atoms_used": atoms_used or [],
        "result": result or {},
        "evidence": evidence or [],
        "limitations": limitations or [],
        "answer_outline": answer_outline or [],
    }
    if message_cn:
        payload["message_cn"] = message_cn
    return payload
