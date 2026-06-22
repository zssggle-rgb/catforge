"""Repository helpers for CatForge analyst commands."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import ResolvedSku
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11D_RULE_VERSION,
)


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

    def sku_fact_brief(
        self,
        *,
        batch_id: str,
        sku: ResolvedSku,
        product_category: str,
        market_window: str,
        analysis_population: str,
        allocation_limit: int = 20,
    ) -> dict[str, Any]:
        product_category = product_category.upper()
        market = self._market_profile(batch_id=batch_id, sku_code=sku.sku_code, market_window=market_window)
        param_profile = self._param_profile(batch_id=batch_id, product_category=product_category, sku_code=sku.sku_code)
        claim_profile = self._claim_profile(batch_id=batch_id, product_category=product_category, sku_code=sku.sku_code)
        comment_profile = self._comment_profile(batch_id=batch_id, product_category=product_category, sku_code=sku.sku_code)
        user_task_profile = self._user_task_profile(batch_id=batch_id, product_category=product_category, sku_code=sku.sku_code)
        target_group_profile = self._target_group_profile(batch_id=batch_id, product_category=product_category, sku_code=sku.sku_code)
        battlefield_profile = self._battlefield_profile(batch_id=batch_id, product_category=product_category, sku_code=sku.sku_code)
        semantic_allocations = self._semantic_allocations(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku.sku_code,
            analysis_population=analysis_population,
            market_window=market_window,
            limit=allocation_limit,
        )
        sections = {
            "market": _market_payload(market),
            "parameter_fact": _param_payload(param_profile),
            "claim_fact": _claim_payload(claim_profile),
            "comment_fact": _comment_payload(comment_profile),
            "user_task": _user_task_payload(user_task_profile),
            "target_group": _target_group_payload(target_group_profile),
            "value_battlefield": _battlefield_payload(battlefield_profile),
            "sales_allocation": [_allocation_payload(row) for row in semantic_allocations],
        }
        missing_sections = [key for key, value in sections.items() if value in ({}, [])]
        evidence_sources = _section_evidence_sources(
            market=market,
            param_profile=param_profile,
            claim_profile=claim_profile,
            comment_profile=comment_profile,
            user_task_profile=user_task_profile,
            target_group_profile=target_group_profile,
            battlefield_profile=battlefield_profile,
            semantic_allocations=semantic_allocations,
        )
        return {
            "sku": {
                "sku_code": sku.sku_code,
                "brand_name": sku.brand_name,
                "model_name": sku.model_name,
                "product_category": product_category,
            },
            "sections": sections,
            "missing_sections": missing_sections,
            "evidence_sources": evidence_sources,
        }

    def semantic_dimension_space(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
        dimension_type: str | None = None,
        dimension_code: str | None = None,
        query: str | None = None,
        brand_name: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(entities.Core3SemanticMarketDimensionSummary)
            .where(entities.Core3SemanticMarketDimensionSummary.project_id == self.project_id)
            .where(entities.Core3SemanticMarketDimensionSummary.category_code == self.category_code)
            .where(entities.Core3SemanticMarketDimensionSummary.batch_id == batch_id)
            .where(entities.Core3SemanticMarketDimensionSummary.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketDimensionSummary.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketDimensionSummary.market_window == market_window)
            .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
        )
        if dimension_type:
            stmt = stmt.where(entities.Core3SemanticMarketDimensionSummary.dimension_type == dimension_type)
        if dimension_code:
            stmt = stmt.where(entities.Core3SemanticMarketDimensionSummary.dimension_code == dimension_code)
        else:
            terms = _query_terms(query)
            if terms:
                stmt = stmt.where(
                    or_(
                        *[
                            func.lower(entities.Core3SemanticMarketDimensionSummary.dimension_code).like(f"%{_escape_like(term.lower())}%", escape="\\")
                            for term in terms
                        ],
                        *[
                            func.lower(entities.Core3SemanticMarketDimensionSummary.dimension_name).like(f"%{_escape_like(term.lower())}%", escape="\\")
                            for term in terms
                        ],
                    )
                )
        stmt = stmt.order_by(
            entities.Core3SemanticMarketDimensionSummary.dimension_type,
            entities.Core3SemanticMarketDimensionSummary.estimated_sales_volume.desc(),
            entities.Core3SemanticMarketDimensionSummary.dimension_code,
        ).limit(200)
        summaries = list(self.db.execute(stmt).scalars())
        return [
            {
                "summary": _semantic_summary_payload(row),
                "sku_contributions": self._semantic_dimension_contributions(
                    batch_id=batch_id,
                    product_category=product_category,
                    analysis_population=analysis_population,
                    market_window=market_window,
                    dimension_type=row.dimension_type,
                    dimension_code=row.dimension_code,
                    brand_name=brand_name,
                    size_tier=size_tier,
                    price_band=price_band,
                    limit=limit,
                ),
            }
            for row in summaries
        ]

    def _market_profile(self, *, batch_id: str, sku_code: str, market_window: str) -> entities.Core3SkuMarketProfile | None:
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.sku_code == sku_code)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _param_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuParamProfile | None:
        rule_version = CORE3_M03B_AC_RULE_VERSION if product_category == "AC" else CORE3_M03B_RULE_VERSION
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.sku_code == sku_code)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _claim_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuClaimFactProfile | None:
        if product_category != "TV":
            return None
        stmt = self._current_sku_profile_stmt(
            entities.Core3SkuClaimFactProfile,
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _comment_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuCommentFactProfile | None:
        if product_category != "TV":
            return None
        stmt = self._current_sku_profile_stmt(
            entities.Core3SkuCommentFactProfile,
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _user_task_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3M09cSkuUserTaskProfile | None:
        if product_category != "TV":
            return None
        stmt = self._current_sku_profile_stmt(
            entities.Core3M09cSkuUserTaskProfile,
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _target_group_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3M10cSkuTargetGroupProfile | None:
        if product_category != "TV":
            return None
        stmt = self._current_sku_profile_stmt(
            entities.Core3M10cSkuTargetGroupProfile,
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _battlefield_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuValueBattlefieldProfile | None:
        if product_category != "TV":
            return None
        stmt = self._current_sku_profile_stmt(
            entities.Core3SkuValueBattlefieldProfile,
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _semantic_allocations(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        analysis_population: str,
        market_window: str,
        limit: int,
    ) -> list[entities.Core3SemanticMarketAllocation]:
        if product_category != "TV":
            return []
        stmt = (
            select(entities.Core3SemanticMarketAllocation)
            .where(entities.Core3SemanticMarketAllocation.project_id == self.project_id)
            .where(entities.Core3SemanticMarketAllocation.category_code == self.category_code)
            .where(entities.Core3SemanticMarketAllocation.batch_id == batch_id)
            .where(entities.Core3SemanticMarketAllocation.product_category == product_category)
            .where(entities.Core3SemanticMarketAllocation.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketAllocation.market_window == market_window)
            .where(entities.Core3SemanticMarketAllocation.sku_code == sku_code)
            .where(entities.Core3SemanticMarketAllocation.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketAllocation.is_current.is_(True))
            .order_by(
                entities.Core3SemanticMarketAllocation.dimension_type,
                entities.Core3SemanticMarketAllocation.allocation_weight.desc(),
                entities.Core3SemanticMarketAllocation.dimension_code,
            )
        )
        if limit != 0:
            stmt = stmt.limit(max(limit, 0))
        return list(self.db.execute(stmt).scalars())

    def _semantic_dimension_contributions(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
        dimension_type: str,
        dimension_code: str,
        brand_name: str | None,
        size_tier: str | None,
        price_band: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if brand_name or size_tier or price_band:
            stmt = (
                select(entities.Core3SemanticMarketAllocation)
                .where(entities.Core3SemanticMarketAllocation.project_id == self.project_id)
                .where(entities.Core3SemanticMarketAllocation.category_code == self.category_code)
                .where(entities.Core3SemanticMarketAllocation.batch_id == batch_id)
                .where(entities.Core3SemanticMarketAllocation.product_category == product_category.upper())
                .where(entities.Core3SemanticMarketAllocation.analysis_population == analysis_population)
                .where(entities.Core3SemanticMarketAllocation.market_window == market_window)
                .where(entities.Core3SemanticMarketAllocation.dimension_type == dimension_type)
                .where(entities.Core3SemanticMarketAllocation.dimension_code == dimension_code)
                .where(entities.Core3SemanticMarketAllocation.rule_version == CORE3_M11D_RULE_VERSION)
                .where(entities.Core3SemanticMarketAllocation.is_current.is_(True))
                .order_by(entities.Core3SemanticMarketAllocation.allocated_sales_volume.desc())
            )
            if brand_name:
                stmt = stmt.where(entities.Core3SemanticMarketAllocation.brand_name == brand_name)
            if size_tier:
                stmt = stmt.where(entities.Core3SemanticMarketAllocation.size_tier == size_tier)
            if price_band:
                stmt = stmt.where(entities.Core3SemanticMarketAllocation.price_band_in_size_tier == price_band)
            if limit != 0:
                stmt = stmt.limit(max(limit, 0))
            return [_allocation_payload(row) for row in self.db.execute(stmt).scalars()]
        stmt = (
            select(entities.Core3SemanticMarketSkuContribution)
            .where(entities.Core3SemanticMarketSkuContribution.project_id == self.project_id)
            .where(entities.Core3SemanticMarketSkuContribution.category_code == self.category_code)
            .where(entities.Core3SemanticMarketSkuContribution.batch_id == batch_id)
            .where(entities.Core3SemanticMarketSkuContribution.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketSkuContribution.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketSkuContribution.market_window == market_window)
            .where(entities.Core3SemanticMarketSkuContribution.dimension_type == dimension_type)
            .where(entities.Core3SemanticMarketSkuContribution.dimension_code == dimension_code)
            .where(entities.Core3SemanticMarketSkuContribution.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketSkuContribution.is_current.is_(True))
            .order_by(
                entities.Core3SemanticMarketSkuContribution.sku_rank_in_dimension,
                entities.Core3SemanticMarketSkuContribution.allocated_sales_volume.desc(),
            )
        )
        if limit != 0:
            stmt = stmt.limit(max(limit, 0))
        return [_semantic_contribution_payload(row) for row in self.db.execute(stmt).scalars()]

    def _current_sku_profile_stmt(
        self,
        model: type[Any],
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        rule_version: str,
    ) -> Any:
        return (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code)
            .where(model.batch_id == batch_id)
            .where(model.product_category == product_category)
            .where(model.sku_code == sku_code)
            .where(model.rule_version == rule_version)
            .where(model.is_current.is_(True))
            .limit(1)
        )

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


def _market_payload(row: entities.Core3SkuMarketProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "analysis_window": row.analysis_window,
        "period": {
            "period_start_raw": row.period_start_raw,
            "period_end_raw": row.period_end_raw,
            "active_week_count": row.active_week_count,
            "market_row_count": row.market_row_count,
            "platform_count": row.platform_count,
        },
        "market_metrics": {
            "sales_volume_total": _number(row.sales_volume_total),
            "sales_amount_total": _number(row.sales_amount_total),
            "avg_weekly_sales_volume": _number(_safe_avg(_decimal(row.sales_volume_total), row.active_week_count)),
            "price_wavg": _number(row.price_wavg),
            "price_latest": _number(row.price_latest),
            "price_median": _number(row.price_median),
            "main_channel_type": row.main_channel_type,
            "main_platform": row.main_platform,
            "platform_share": row.platform_share_json or {},
        },
        "market_position": {
            "screen_size_inch": _number(row.screen_size_inch),
            "size_tier": row.size_segment,
            "price_band_in_size_tier": row.price_band_size,
            "price_percentile_in_size": _number(row.price_percentile_in_size),
            "volume_percentile_in_size": _number(row.volume_percentile_in_size),
            "same_pool_sku_count": row.same_pool_sku_count,
        },
        "quality": {
            "market_confidence": _number(row.market_confidence),
            "confidence_level": row.confidence_level,
            "sample_status": row.sample_status,
            "quality_flags": row.quality_flags or [],
        },
        "evidence_id_count": len(row.evidence_ids or []),
    }


def _param_payload(row: entities.Core3SkuParamProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    values = row.param_values_json or {}
    return {
        "summary": {
            "param_completeness": _number(row.param_completeness),
            "known_param_count": row.known_param_count,
            "unknown_param_count": row.unknown_param_count,
            "conflict_count": row.conflict_count,
            "review_required_count": row.review_required_count,
        },
        "dimension_tier_profile": values.get("dimension_tier_profile") or {},
        "core_params": {
            "picture": row.core_picture_params_json or {},
            "gaming": row.core_gaming_params_json or {},
            "system": row.core_system_params_json or {},
            "eye_care": row.core_eye_care_params_json or {},
        },
        "quality_summary": row.quality_summary_json or {},
        "evidence_id_count": len(row.evidence_ids or []),
    }


def _claim_payload(row: entities.Core3SkuClaimFactProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "summary": {
            "raw_claim_count": row.raw_claim_count,
            "matched_claim_count": row.matched_claim_count,
            "fact_claim_count": row.fact_claim_count,
            "unsupported_claim_count": row.unsupported_claim_count,
            "service_separate_claim_count": row.service_separate_claim_count,
            "confidence": _number(row.confidence),
        },
        "claim_codes": row.claim_codes or [],
        "fact_claim_codes": row.fact_claim_codes or [],
        "unsupported_claim_codes": row.unsupported_claim_codes or [],
        "dimension_profile": row.dimension_profile_json or {},
        "dimension_position_profile": row.dimension_position_profile_json or {},
        "claim_summary": row.claim_summary_json or {},
        "quality_flags": row.quality_flags or [],
        "evidence_id_count": len(row.evidence_ids or []),
    }


def _comment_payload(row: entities.Core3SkuCommentFactProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "summary": {
            "comment_sentence_count": row.comment_sentence_count,
            "matched_sentence_count": row.matched_sentence_count,
            "fact_atom_count": row.fact_atom_count,
            "product_fact_sentence_count": row.product_fact_sentence_count,
            "positive_sentence_count": row.positive_sentence_count,
            "negative_sentence_count": row.negative_sentence_count,
            "service_excluded_sentence_count": row.service_excluded_sentence_count,
            "confidence": _number(row.confidence),
        },
        "dimension_summary": row.dimension_summary_json or {},
        "signal_summary": row.signal_summary_json or {},
        "param_comment_support": row.param_comment_support_json or {},
        "claim_comment_support": row.claim_comment_support_json or {},
        "supported_param_codes": row.supported_param_codes or [],
        "contradicted_param_codes": row.contradicted_param_codes or [],
        "supported_claim_codes": row.supported_claim_codes or [],
        "contradicted_claim_codes": row.contradicted_claim_codes or [],
        "evidence_examples": (row.evidence_examples_json or [])[:5],
        "quality_flags": row.quality_flags or [],
        "evidence_id_count": len(row.evidence_ids or []),
    }


def _user_task_payload(row: entities.Core3M09cSkuUserTaskProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "primary_user_task_code": row.primary_user_task_code,
        "primary_relation_status": row.primary_relation_status,
        "secondary_user_task_codes": row.secondary_user_task_codes_json or [],
        "comment_observed_task_codes": row.comment_observed_task_codes_json or [],
        "brand_claimed_task_codes": row.brand_claimed_task_codes_json or [],
        "latent_capability_task_codes": row.latent_capability_task_codes_json or [],
        "drag_factor_task_codes": row.drag_factor_task_codes_json or [],
        "summary": row.user_task_summary_json or {},
        "no_primary_reason": row.no_primary_reason,
        "confidence": _number(row.confidence),
        "evidence_id_count": len(row.evidence_ids_json or []),
    }


def _target_group_payload(row: entities.Core3M10cSkuTargetGroupProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "primary_target_group_code": row.primary_target_group_code,
        "primary_relation_status": row.primary_relation_status,
        "secondary_target_group_codes": row.secondary_target_group_codes_json or [],
        "comment_observed_group_codes": row.comment_observed_group_codes_json or [],
        "brand_claimed_group_codes": row.brand_claimed_group_codes_json or [],
        "latent_group_codes": row.latent_group_codes_json or [],
        "unmet_group_need_codes": row.unmet_group_need_codes_json or [],
        "summary": row.target_group_summary_json or {},
        "confidence": _number(row.confidence),
        "evidence_id_count": len(row.evidence_ids_json or []),
    }


def _battlefield_payload(row: entities.Core3SkuValueBattlefieldProfile | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "primary_battlefield_code": row.primary_battlefield_code,
        "primary_relation_status": row.primary_relation_status,
        "secondary_battlefield_codes": row.secondary_battlefield_codes_json or [],
        "opportunity_battlefield_codes": row.opportunity_battlefield_codes_json or [],
        "drag_factor_battlefield_codes": row.drag_factor_battlefield_codes_json or [],
        "summary": row.battlefield_summary_json or {},
        "confidence": _number(row.confidence),
        "evidence_id_count": len(row.evidence_ids_json or []),
    }


def _semantic_summary_payload(row: entities.Core3SemanticMarketDimensionSummary) -> dict[str, Any]:
    return {
        "dimension_type": row.dimension_type,
        "dimension_code": row.dimension_code,
        "dimension_name": row.dimension_name,
        "taxonomy_version": row.taxonomy_version,
        "sku_relation_count": row.sku_relation_count,
        "allocated_sku_count": row.allocated_sku_count,
        "primary_sku_count": row.primary_sku_count,
        "secondary_sku_count": row.secondary_sku_count,
        "observed_need_sku_count": row.observed_need_sku_count,
        "brand_claim_sku_count": row.brand_claim_sku_count,
        "opportunity_sku_count": row.opportunity_sku_count,
        "drag_risk_sku_count": row.drag_risk_sku_count,
        "estimated_sales_volume": _number(row.estimated_sales_volume),
        "estimated_sales_amount": _number(row.estimated_sales_amount),
        "estimated_avg_weekly_sales_volume": _number(row.estimated_avg_weekly_sales_volume),
        "estimated_avg_weekly_sales_amount": _number(row.estimated_avg_weekly_sales_amount),
        "sales_volume_share": _number(row.sales_volume_share),
        "sales_amount_share": _number(row.sales_amount_share),
        "allocation_coverage_rate": _number(row.allocation_coverage_rate),
        "brand_distribution": row.brand_distribution_json or {},
        "size_price_distribution": row.size_price_distribution_json or {},
        "relation_status_counts": row.relation_status_counts_json or {},
        "top_skus": row.top_skus_json or [],
        "confidence_avg": _number(row.confidence_avg),
        "business_summary_cn": row.business_summary_cn,
    }


def _semantic_contribution_payload(row: entities.Core3SemanticMarketSkuContribution) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "dimension_type": row.dimension_type,
        "dimension_code": row.dimension_code,
        "dimension_name": row.dimension_name,
        "sku_rank_in_dimension": row.sku_rank_in_dimension,
        "allocation_weight": _number(row.allocation_weight),
        "allocated_sales_volume": _number(row.allocated_sales_volume),
        "allocated_sales_amount": _number(row.allocated_sales_amount),
        "allocated_avg_weekly_sales_volume": _number(row.allocated_avg_weekly_sales_volume),
        "allocated_avg_weekly_sales_amount": _number(row.allocated_avg_weekly_sales_amount),
        "sku_share_in_dimension_volume": _number(row.sku_share_in_dimension_volume),
        "sku_share_in_dimension_amount": _number(row.sku_share_in_dimension_amount),
        "is_primary_dimension": row.is_primary_dimension,
        "allocation_role": row.allocation_role,
        "relation_status": row.relation_status,
        "allocation_confidence": _number(row.allocation_confidence),
        "contribution_reason_cn": row.contribution_reason_cn,
        "evidence_id_count": len(row.evidence_ids_json or []),
    }


def _allocation_payload(row: entities.Core3SemanticMarketAllocation) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "dimension_type": row.dimension_type,
        "dimension_code": row.dimension_code,
        "dimension_name": row.dimension_name,
        "size_tier": row.size_tier,
        "price_band_in_size_tier": row.price_band_in_size_tier,
        "relation_status": row.relation_status,
        "allocation_role": row.allocation_role,
        "allocation_value_type": row.allocation_value_type,
        "final_score": _number(row.final_score),
        "allocation_weight": _number(row.allocation_weight),
        "sales_volume_total": _number(row.sales_volume_total),
        "sales_amount_total": _number(row.sales_amount_total),
        "avg_weekly_sales_volume": _number(row.avg_weekly_sales_volume),
        "allocated_sales_volume": _number(row.allocated_sales_volume),
        "allocated_sales_amount": _number(row.allocated_sales_amount),
        "allocated_avg_weekly_sales_volume": _number(row.allocated_avg_weekly_sales_volume),
        "allocated_avg_weekly_sales_amount": _number(row.allocated_avg_weekly_sales_amount),
        "allocation_confidence": _number(row.allocation_confidence),
        "allocation_basis": row.allocation_basis_json or {},
        "evidence_id_count": len(row.evidence_ids_json or []),
    }


def _section_evidence_sources(**sections: Any) -> list[dict[str, Any]]:
    module_by_key = {
        "market": "M07",
        "param_profile": "M03B",
        "claim_profile": "M04C",
        "comment_profile": "M05C",
        "user_task_profile": "M09C",
        "target_group_profile": "M10C",
        "battlefield_profile": "M11C",
        "semantic_allocations": "M11D",
    }
    sources: list[dict[str, Any]] = []
    for key, value in sections.items():
        if not value:
            continue
        if isinstance(value, list):
            evidence_count = sum(len(getattr(item, "evidence_ids_json", []) or []) for item in value)
            row_count = len(value)
        else:
            evidence_count = len((getattr(value, "evidence_ids", None) or getattr(value, "evidence_ids_json", None) or []))
            row_count = 1
        sources.append({"source_module": module_by_key[key], "row_count": row_count, "evidence_id_count": evidence_count})
    return sources


def _query_terms(query: str | None) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []
    return [part for part in re.split(r"[\s,，/]+", text) if part]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _number(value: object) -> float | None:
    decimal_value = _decimal(value)
    if decimal_value is None:
        return None
    return float(decimal_value)
