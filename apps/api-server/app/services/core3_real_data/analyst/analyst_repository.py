"""Repository helpers for CatForge analyst commands."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Sequence

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import ResolvedSku
from app.services.core3_real_data.constants import CORE3_M03B_AC_RULE_VERSION, CORE3_M03B_RULE_VERSION, CORE3_M07_RULE_VERSION


SKU_CODE_RE = re.compile(r"\b(?:TV|AC)\d{6,}\b", re.IGNORECASE)


class AnalystRepository:
    def __init__(self, db: Session, *, project_id: str, category_code: str) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = category_code

    def latest_batch_id(self) -> str | None:
        stmt = (
            select(entities.Core3SourceBatch.batch_id)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code)
            .order_by(desc(entities.Core3SourceBatch.scan_started_at), desc(entities.Core3SourceBatch.batch_id))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def resolve_sku(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str,
        query: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        limit: int = 10,
    ) -> list[ResolvedSku]:
        normalized_category = product_category.upper()
        requested_sku = self._extract_sku_code(query=query, sku_code=sku_code)
        if requested_sku and not requested_sku.startswith(self._sku_prefix(normalized_category)):
            return []
        requested_model = (model_name or "").strip() or self._extract_model_query(query=query)
        market_matches = self._resolve_from_market(
            batch_id=batch_id,
            product_category=normalized_category,
            market_window=market_window,
            sku_code=requested_sku,
            model_name=requested_model,
            limit=limit,
        )
        if market_matches:
            return market_matches
        return self._resolve_from_param_profile(
            batch_id=batch_id,
            product_category=normalized_category,
            sku_code=requested_sku,
            model_name=requested_model,
            limit=limit,
        )

    def _resolve_from_market(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str,
        sku_code: str | None,
        model_name: str | None,
        limit: int,
    ) -> list[ResolvedSku]:
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
        )
        if sku_code:
            stmt = stmt.where(entities.Core3SkuMarketProfile.sku_code == sku_code.upper())
        elif model_name:
            like_value = f"%{model_name}%"
            stmt = stmt.where(
                or_(
                    entities.Core3SkuMarketProfile.model_name == model_name,
                    entities.Core3SkuMarketProfile.model_name.ilike(like_value),
                )
            )
            stmt = stmt.where(entities.Core3SkuMarketProfile.sku_code.like(f"{self._sku_prefix(product_category)}%"))
        else:
            return []
        stmt = stmt.order_by(entities.Core3SkuMarketProfile.sku_code).limit(limit)
        rows = list(self.db.execute(stmt).scalars())
        return [
            ResolvedSku(
                sku_code=row.sku_code,
                brand_name=row.brand_name or row.brand,
                model_name=row.model_name,
                product_category=product_category,
                size_tier=row.size_segment or row.screen_size_class or row.market_pool_key,
                price_band_in_size_tier=row.price_band_size or row.price_band_category,
                screen_size_inch=_decimal(row.screen_size_inch),
                weighted_price=_decimal(row.price_wavg),
                avg_weekly_sales_volume=_safe_avg(_decimal(row.sales_volume_total), row.active_week_count),
                source="M07",
            )
            for row in rows
        ]

    def _resolve_from_param_profile(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str | None,
        model_name: str | None,
        limit: int,
    ) -> list[ResolvedSku]:
        rule_version = CORE3_M03B_AC_RULE_VERSION if product_category == "AC" else CORE3_M03B_RULE_VERSION
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
        )
        if sku_code:
            stmt = stmt.where(entities.Core3SkuParamProfile.sku_code == sku_code.upper())
        elif model_name:
            like_value = f"%{model_name}%"
            stmt = stmt.where(
                or_(
                    entities.Core3SkuParamProfile.model_name == model_name,
                    entities.Core3SkuParamProfile.model_name.ilike(like_value),
                )
            )
            stmt = stmt.where(entities.Core3SkuParamProfile.sku_code.like(f"{self._sku_prefix(product_category)}%"))
        else:
            return []
        stmt = stmt.order_by(entities.Core3SkuParamProfile.sku_code).limit(limit)
        rows = list(self.db.execute(stmt).scalars())
        return [
            ResolvedSku(
                sku_code=row.sku_code,
                brand_name=None,
                model_name=row.model_name,
                product_category=product_category,
                size_tier=(row.param_values_json or {}).get("dimension_tier_profile", {}).get("size"),
                source="M03B",
            )
            for row in rows
        ]

    @staticmethod
    def _extract_sku_code(*, query: str | None, sku_code: str | None) -> str | None:
        if sku_code:
            return sku_code.upper()
        if not query:
            return None
        match = SKU_CODE_RE.search(query)
        return match.group(0).upper() if match else None

    @staticmethod
    def _extract_model_query(*, query: str | None) -> str | None:
        text = (query or "").strip()
        if not text or SKU_CODE_RE.search(text):
            return None
        return text

    @staticmethod
    def _sku_prefix(product_category: str) -> str:
        return "AC" if product_category == "AC" else "TV"


def unique_skus(candidates: Sequence[ResolvedSku]) -> list[ResolvedSku]:
    seen: set[str] = set()
    result: list[ResolvedSku] = []
    for candidate in candidates:
        if candidate.sku_code in seen:
            continue
        seen.add(candidate.sku_code)
        result.append(candidate)
    return result


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _safe_avg(total: Decimal | None, count: int | None) -> Decimal | None:
    if total is None or not count:
        return None
    if count <= 0:
        return None
    return total / Decimal(count)
