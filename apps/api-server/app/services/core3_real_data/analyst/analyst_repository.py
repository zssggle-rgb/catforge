"""Repository helpers for CatForge analyst commands."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import ResolvedSku
from app.services.core3_real_data.analyst.competitor_answer import weighted_overlap_from_roles
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
    CORE3_M12C_RULE_VERSION,
)


SKU_CODE_RE = re.compile(r"\b(?:TV|AC)\d{6,}\b", re.IGNORECASE)
MODEL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{2,3}[A-Za-z][A-Za-z0-9-]*(?:\s*(?:PRO|PLUS|MAX|MINI|\+))?|[A-Za-z]{1,8}\d{2,3}[A-Za-z0-9-]*(?:\s*(?:PRO|PLUS|MAX|MINI|\+))?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
BRAND_QUERY_WORDS = (
    "海信",
    "hisense",
    "vidda",
    "创维",
    "skyworth",
    "tcl",
    "小米",
    "xiaomi",
    "redmi",
    "红米",
    "华为",
    "huawei",
    "索尼",
    "sony",
    "三星",
    "samsung",
    "雷鸟",
    "ffalcon",
    "长虹",
    "changhong",
    "康佳",
    "konka",
)

M12C_ROLE_PREMIUM = "premium_driver_estimated"
M12C_ROLE_SALES = "sales_driver_estimated"
M12C_ROLE_BASIC = "basic_threshold"
M12C_ROLE_VALUE_BUNDLE = "value_bundle_claim"
M12C_ROLE_WEAK_USER = "weak_user_perception_claim"
M12C_ROLE_HIGH_PRICE_INTERCEPT = "high_price_competitor_intercept"
M12C_ROLE_PRICE_UP = "price_up_opportunity"
M12C_ROLE_BRAND = "brand_claim_only"
M12C_ROLE_USER_NEED = "user_validated_need"
M12C_ROLE_DRAG = "drag_factor"
M12C_ROLE_OPPORTUNITY = "opportunity_gap"
M12C_ROLE_SAMPLE = "sample_insufficient"

M12C_POSITIVE_ROLES = {M12C_ROLE_PREMIUM, M12C_ROLE_SALES, M12C_ROLE_VALUE_BUNDLE}
M12C_GAP_ROLES = {
    M12C_ROLE_OPPORTUNITY,
    M12C_ROLE_DRAG,
    M12C_ROLE_WEAK_USER,
    M12C_ROLE_HIGH_PRICE_INTERCEPT,
    M12C_ROLE_PRICE_UP,
}
M12C_ROLE_PRIORITY = {
    M12C_ROLE_PREMIUM: 0,
    M12C_ROLE_SALES: 1,
    M12C_ROLE_VALUE_BUNDLE: 2,
    M12C_ROLE_BASIC: 3,
    M12C_ROLE_HIGH_PRICE_INTERCEPT: 4,
    M12C_ROLE_PRICE_UP: 5,
    M12C_ROLE_WEAK_USER: 6,
    M12C_ROLE_USER_NEED: 7,
    M12C_ROLE_DRAG: 8,
    M12C_ROLE_OPPORTUNITY: 9,
    M12C_ROLE_BRAND: 10,
    M12C_ROLE_SAMPLE: 11,
}


class AnalystRepository:
    def __init__(self, db: Session, *, project_id: str, category_code: str) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = category_code

    def latest_batch_id(self) -> str | None:
        ready_batch = self._latest_semantic_market_batch_id()
        if ready_batch:
            return ready_batch
        market_batch = self._latest_market_profile_batch_id()
        if market_batch:
            return market_batch
        stmt = (
            select(entities.Core3SourceBatch.batch_id)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code)
            .order_by(desc(entities.Core3SourceBatch.scan_started_at), desc(entities.Core3SourceBatch.batch_id))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _latest_semantic_market_batch_id(self) -> str | None:
        stmt = (
            select(entities.Core3SourceBatch.batch_id)
            .join(
                entities.Core3SemanticMarketDimensionSummary,
                (entities.Core3SemanticMarketDimensionSummary.project_id == entities.Core3SourceBatch.project_id)
                & (entities.Core3SemanticMarketDimensionSummary.category_code == entities.Core3SourceBatch.category_code)
                & (entities.Core3SemanticMarketDimensionSummary.batch_id == entities.Core3SourceBatch.batch_id),
            )
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code)
            .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
            .group_by(entities.Core3SourceBatch.batch_id, entities.Core3SourceBatch.scan_started_at)
            .having(func.count(entities.Core3SemanticMarketDimensionSummary.summary_id) > 0)
            .order_by(desc(entities.Core3SourceBatch.scan_started_at), desc(entities.Core3SourceBatch.batch_id))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _latest_market_profile_batch_id(self) -> str | None:
        stmt = (
            select(entities.Core3SourceBatch.batch_id)
            .join(
                entities.Core3SkuMarketProfile,
                (entities.Core3SkuMarketProfile.project_id == entities.Core3SourceBatch.project_id)
                & (entities.Core3SkuMarketProfile.category_code == entities.Core3SourceBatch.category_code)
                & (entities.Core3SkuMarketProfile.batch_id == entities.Core3SourceBatch.batch_id),
            )
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .group_by(entities.Core3SourceBatch.batch_id, entities.Core3SourceBatch.scan_started_at)
            .having(func.count(entities.Core3SkuMarketProfile.profile_id) > 0)
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
        requested_model = self._normalize_requested_model((model_name or "").strip() or self._extract_model_query(query=query))
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
        base_stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
        )
        if sku_code:
            stmt = base_stmt.where(entities.Core3SkuMarketProfile.sku_code == sku_code.upper())
            rows = list(self.db.execute(stmt.order_by(entities.Core3SkuMarketProfile.sku_code).limit(limit)).scalars())
        elif model_name:
            sku_prefix_filter = entities.Core3SkuMarketProfile.sku_code.like(f"{self._sku_prefix(product_category)}%")
            rows = []
            for model_variant in _model_query_variants(model_name):
                exact_stmt = (
                    base_stmt.where(entities.Core3SkuMarketProfile.model_name.ilike(model_variant))
                    .where(sku_prefix_filter)
                    .order_by(entities.Core3SkuMarketProfile.sku_code)
                    .limit(limit)
                )
                exact_rows = _exact_model_rows(list(self.db.execute(exact_stmt).scalars()), model_variant)
                if len(exact_rows) == 1:
                    rows = exact_rows
                    break
            if not rows:
                for model_variant in _model_query_variants(model_name):
                    like_value = f"%{_model_like_anchor(model_variant)}%"
                    stmt = (
                        base_stmt.where(entities.Core3SkuMarketProfile.model_name.ilike(like_value))
                        .where(sku_prefix_filter)
                        .order_by(entities.Core3SkuMarketProfile.sku_code)
                        .limit(max(limit * 5, 50))
                    )
                    rows = _rank_model_rows(list(self.db.execute(stmt).scalars()), model_variant)[:limit]
                    if rows:
                        break
        else:
            return []
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
        base_stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
        )
        if sku_code:
            stmt = base_stmt.where(entities.Core3SkuParamProfile.sku_code == sku_code.upper())
            rows = list(self.db.execute(stmt.order_by(entities.Core3SkuParamProfile.sku_code).limit(limit)).scalars())
        elif model_name:
            sku_prefix_filter = entities.Core3SkuParamProfile.sku_code.like(f"{self._sku_prefix(product_category)}%")
            rows = []
            for model_variant in _model_query_variants(model_name):
                exact_stmt = (
                    base_stmt.where(entities.Core3SkuParamProfile.model_name.ilike(model_variant))
                    .where(sku_prefix_filter)
                    .order_by(entities.Core3SkuParamProfile.sku_code)
                    .limit(limit)
                )
                exact_rows = _exact_model_rows(list(self.db.execute(exact_stmt).scalars()), model_variant)
                if len(exact_rows) == 1:
                    rows = exact_rows
                    break
            if not rows:
                for model_variant in _model_query_variants(model_name):
                    like_value = f"%{_model_like_anchor(model_variant)}%"
                    stmt = (
                        base_stmt.where(entities.Core3SkuParamProfile.model_name.ilike(like_value))
                        .where(sku_prefix_filter)
                        .order_by(entities.Core3SkuParamProfile.sku_code)
                        .limit(max(limit * 5, 50))
                    )
                    rows = _rank_model_rows(list(self.db.execute(stmt).scalars()), model_variant)[:limit]
                    if rows:
                        break
        else:
            return []
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
        fact_size_tier = _param_size_tier(param_profile)
        market_payload = _market_payload(market)
        if market_payload and fact_size_tier:
            market_position = market_payload.setdefault("market_position", {})
            market_size_tier = market_position.get("size_tier")
            market_position["size_tier"] = fact_size_tier
            if market_size_tier and market_size_tier != fact_size_tier:
                market_position["market_size_tier"] = market_size_tier
                market_position["size_tier_note_cn"] = "尺寸段优先采用 M03B 参数事实画像五档口径，M07 原市场池字段保留为 market_size_tier。"
        if market_payload:
            market_payload["market_pool"] = self._market_pool_summary(
                batch_id=batch_id,
                market=market,
                product_category=product_category,
                market_window=market_window,
                size_tier=fact_size_tier,
            )
        sections = {
            "market": market_payload,
            "parameter_fact": _param_payload(param_profile),
            "claim_fact": _claim_payload(claim_profile),
            "comment_fact": _comment_payload(comment_profile),
            "user_task": _user_task_payload(user_task_profile),
            "target_group": _target_group_payload(target_group_profile),
            "value_battlefield": _battlefield_payload(battlefield_profile),
            "sales_allocation": [_allocation_payload(row) for row in semantic_allocations],
            "semantic_dimension_positions": self._semantic_dimension_positions(
                batch_id=batch_id,
                product_category=product_category,
                sku_code=sku.sku_code,
                analysis_population=analysis_population,
                market_window=market_window,
                allocations=semantic_allocations,
                user_task_profile=user_task_profile,
                target_group_profile=target_group_profile,
                battlefield_profile=battlefield_profile,
            ),
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

    def same_size_price_candidates(
        self,
        *,
        batch_id: str,
        target_sku_code: str,
        product_category: str,
        market_window: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        target_market = self._market_profile(batch_id=batch_id, sku_code=target_sku_code, market_window=market_window)
        if target_market is None:
            return {"target_market": {}, "candidates": [], "match_policy": "m07_same_size_price_band"}
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .where(entities.Core3SkuMarketProfile.sku_code != target_sku_code)
            .where(entities.Core3SkuMarketProfile.sku_code.like(f"{self._sku_prefix(product_category.upper())}%"))
            .where(entities.Core3SkuMarketProfile.size_segment == target_market.size_segment)
            .order_by(
                func.abs(entities.Core3SkuMarketProfile.price_wavg - target_market.price_wavg),
                entities.Core3SkuMarketProfile.sales_volume_total.desc(),
                entities.Core3SkuMarketProfile.sku_code,
            )
        )
        if limit != 0:
            stmt = stmt.limit(max(limit * 5, limit, 50))
        rows = sorted(
            list(self.db.execute(stmt).scalars()),
            key=lambda row: _candidate_pool_sort_key(row, target_market),
        )
        if limit != 0:
            rows = rows[: max(limit, 0)]
        return {
            "target_market": _candidate_market_payload(target_market, target_market=target_market),
            "match_policy": "m07_same_size_price_band",
            "candidates": [_candidate_market_payload(row, target_market=target_market) for row in rows],
        }

    def semantic_overlap(
        self,
        *,
        batch_id: str,
        product_category: str,
        target_sku_code: str,
        candidate_sku_code: str,
    ) -> dict[str, Any]:
        target_task = self._user_task_profile(batch_id=batch_id, product_category=product_category, sku_code=target_sku_code)
        candidate_task = self._user_task_profile(batch_id=batch_id, product_category=product_category, sku_code=candidate_sku_code)
        target_group = self._target_group_profile(batch_id=batch_id, product_category=product_category, sku_code=target_sku_code)
        candidate_group = self._target_group_profile(batch_id=batch_id, product_category=product_category, sku_code=candidate_sku_code)
        target_battlefield = self._battlefield_profile(batch_id=batch_id, product_category=product_category, sku_code=target_sku_code)
        candidate_battlefield = self._battlefield_profile(batch_id=batch_id, product_category=product_category, sku_code=candidate_sku_code)
        overlap = {
            "user_task": _code_overlap(
                _user_task_code_roles(target_task),
                _user_task_code_roles(candidate_task),
                primary_key="primary_user_task_code",
            ),
            "target_group": _code_overlap(
                _target_group_code_roles(target_group),
                _target_group_code_roles(candidate_group),
                primary_key="primary_target_group_code",
            ),
            "value_battlefield": _code_overlap(
                _battlefield_code_roles(target_battlefield),
                _battlefield_code_roles(candidate_battlefield),
                primary_key="primary_battlefield_code",
            ),
        }
        scores = [_decimal(item["overlap_score"]) or Decimal("0") for item in overlap.values() if item["union_count"]]
        return {
            "target_sku_code": target_sku_code,
            "candidate_sku_code": candidate_sku_code,
            "semantic_overlap_score": _number(_avg_decimal(scores)),
            "overlap": overlap,
            "source_modules": ["M09C", "M10C", "M11C"],
        }

    def sales_overlap(
        self,
        *,
        batch_id: str,
        target_sku_code: str,
        candidate_sku_code: str,
        market_window: str,
    ) -> dict[str, Any]:
        weekly_rows = self._market_weekly_rows(batch_id=batch_id, sku_codes=(target_sku_code, candidate_sku_code))
        weekly_by_sku = _weekly_market_by_sku(weekly_rows)
        target_weeks = set(weekly_by_sku.get(target_sku_code, {}))
        candidate_weeks = set(weekly_by_sku.get(candidate_sku_code, {}))
        overlap_weeks = sorted(target_weeks & candidate_weeks)
        if overlap_weeks:
            target_values = [weekly_by_sku[target_sku_code][week] for week in overlap_weeks]
            candidate_values = [weekly_by_sku[candidate_sku_code][week] for week in overlap_weeks]
            target_avg_volume = _avg_decimal([item["sales_volume"] for item in target_values])
            candidate_avg_volume = _avg_decimal([item["sales_volume"] for item in candidate_values])
            target_avg_amount = _avg_decimal([item["sales_amount"] for item in target_values])
            candidate_avg_amount = _avg_decimal([item["sales_amount"] for item in candidate_values])
            return {
                "method": "pairwise_overlap_active_week_average",
                "policy_note_cn": "销量/销额对比使用两款 SKU 重叠在售周的周均表现；累计销量仅作为展示上下文。",
                "target_sku_code": target_sku_code,
                "candidate_sku_code": candidate_sku_code,
                "overlap_weeks": overlap_weeks,
                "overlap_week_count": len(overlap_weeks),
                "target": _sales_overlap_side(target_sku_code, target_values, target_avg_volume, target_avg_amount),
                "candidate": _sales_overlap_side(candidate_sku_code, candidate_values, candidate_avg_volume, candidate_avg_amount),
                "comparison": _sales_comparison(target_avg_volume, candidate_avg_volume, target_avg_amount, candidate_avg_amount),
            }
        return self._sales_overlap_market_fallback(
            batch_id=batch_id,
            target_sku_code=target_sku_code,
            candidate_sku_code=candidate_sku_code,
            market_window=market_window,
        )

    def param_claim_overlap(
        self,
        *,
        batch_id: str,
        product_category: str,
        target_sku_code: str,
        candidate_sku_code: str,
    ) -> dict[str, Any]:
        target_param = self._param_profile(batch_id=batch_id, product_category=product_category, sku_code=target_sku_code)
        candidate_param = self._param_profile(batch_id=batch_id, product_category=product_category, sku_code=candidate_sku_code)
        target_claim = self._claim_profile(batch_id=batch_id, product_category=product_category, sku_code=target_sku_code)
        candidate_claim = self._claim_profile(batch_id=batch_id, product_category=product_category, sku_code=candidate_sku_code)
        param_overlap = _code_overlap(_param_code_roles(target_param), _param_code_roles(candidate_param), primary_key=None)
        claim_overlap = _code_overlap(_claim_code_roles(target_claim), _claim_code_roles(candidate_claim), primary_key=None)
        position_overlap = _code_overlap(
            _claim_position_roles(target_claim),
            _claim_position_roles(candidate_claim),
            primary_key=None,
        )
        scores = [_decimal(item["overlap_score"]) or Decimal("0") for item in (param_overlap, claim_overlap, position_overlap) if item["union_count"]]
        return {
            "target_sku_code": target_sku_code,
            "candidate_sku_code": candidate_sku_code,
            "param_claim_overlap_score": _number(_avg_decimal(scores)),
            "parameter_overlap": param_overlap,
            "claim_overlap": claim_overlap,
            "claim_position_overlap": position_overlap,
            "source_modules": ["M03B", "M04C"],
        }

    def comment_support(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        claim_code: str | None = None,
        param_code: str | None = None,
        user_task_code: str | None = None,
        target_group_code: str | None = None,
        battlefield_code: str | None = None,
    ) -> dict[str, Any]:
        comment = self._comment_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        task = self._user_task_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        group = self._target_group_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        battlefield = self._battlefield_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        if comment is None:
            return {"sku_code": sku_code, "comment_profile": {}, "support_items": [], "available_summary": {}}
        support_items: list[dict[str, Any]] = []
        if param_code:
            support_items.append(_comment_param_support(comment, param_code))
        if claim_code:
            support_items.append(_comment_claim_support(comment, claim_code))
        if user_task_code:
            support_items.append(_comment_profile_code_support("user_task", user_task_code, _user_task_code_roles(task)))
        if target_group_code:
            support_items.append(_comment_profile_code_support("target_group", target_group_code, _target_group_code_roles(group)))
        if battlefield_code:
            support_items.append(_comment_profile_code_support("battlefield", battlefield_code, _battlefield_code_roles(battlefield)))
        return {
            "sku_code": sku_code,
            "comment_profile": _comment_payload(comment),
            "support_items": support_items,
            "available_summary": {
                "supported_param_codes": comment.supported_param_codes or [],
                "contradicted_param_codes": comment.contradicted_param_codes or [],
                "supported_claim_codes": comment.supported_claim_codes or [],
                "contradicted_claim_codes": comment.contradicted_claim_codes or [],
                "comment_observed_task_codes": (task.comment_observed_task_codes_json or []) if task else [],
                "comment_observed_group_codes": (group.comment_observed_group_codes_json or []) if group else [],
                "drag_factor_battlefield_codes": (battlefield.drag_factor_battlefield_codes_json or []) if battlefield else [],
            },
        }

    def opportunity_gaps(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        market_window: str,
        analysis_population: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        market = self._market_profile(batch_id=batch_id, sku_code=sku_code, market_window=market_window)
        param = self._param_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        claim = self._claim_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        comment = self._comment_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        task = self._user_task_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        group = self._target_group_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        battlefield = self._battlefield_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        allocations = self._semantic_allocations(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            analysis_population=analysis_population,
            market_window=market_window,
            limit=limit,
        )
        battlefield_codes = _opportunity_dimension_codes(battlefield, allocations)
        summaries = self._semantic_summaries_by_codes(
            batch_id=batch_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            dimension_type="battlefield",
            dimension_codes=battlefield_codes,
        )
        summary_by_code = {row.dimension_code: row for row in summaries}
        allocation_by_code = {row.dimension_code: row for row in allocations}
        established_codes = _unique_codes(
            [battlefield.primary_battlefield_code if battlefield else None],
            battlefield.secondary_battlefield_codes_json if battlefield else [],
        )
        opportunity_codes = _unique_codes(battlefield.opportunity_battlefield_codes_json if battlefield else [])
        drag_codes = _unique_codes(battlefield.drag_factor_battlefield_codes_json if battlefield else [])
        observed_codes = _unique_codes(
            [row.dimension_code for row in allocations if row.relation_status == "user_observed_battlefield"]
        )
        return {
            "sku_code": sku_code,
            "market_position": _opportunity_market_position(market, param),
            "established_battlefields": _dimension_gap_items(
                established_codes,
                summary_by_code=summary_by_code,
                allocation_by_code=allocation_by_code,
                default_relation_status="established_battlefield",
            ),
            "opportunity_battlefields": _dimension_gap_items(
                opportunity_codes,
                summary_by_code=summary_by_code,
                allocation_by_code=allocation_by_code,
                default_relation_status="opportunity_battlefield",
            ),
            "user_observed_battlefields": _dimension_gap_items(
                observed_codes,
                summary_by_code=summary_by_code,
                allocation_by_code=allocation_by_code,
                default_relation_status="user_observed_battlefield",
            ),
            "drag_factor_battlefields": _dimension_gap_items(
                drag_codes,
                summary_by_code=summary_by_code,
                allocation_by_code=allocation_by_code,
                default_relation_status="drag_factor_battlefield",
            ),
            "price_gap_signals": _price_gap_signals(market),
            "param_gap_signals": _param_gap_signals(param, comment),
            "claim_gap_signals": _claim_gap_signals(claim, comment),
            "comment_gap_signals": _comment_gap_signals(comment),
            "semantic_gap_signals": _semantic_gap_signals(task, group, battlefield),
            "source_profiles": {
                "market": _market_payload(market),
                "parameter_fact": _param_payload(param),
                "claim_fact": _claim_payload(claim),
                "comment_fact": _comment_payload(comment),
                "user_task": _user_task_payload(task),
                "target_group": _target_group_payload(group),
                "value_battlefield": _battlefield_payload(battlefield),
                "sales_allocations": [_allocation_payload(row) for row in allocations],
            },
            "evidence_sources": _section_evidence_sources(
                market=market,
                param_profile=param,
                claim_profile=claim,
                comment_profile=comment,
                user_task_profile=task,
                target_group_profile=group,
                battlefield_profile=battlefield,
                semantic_allocations=allocations,
            ),
        }

    def claim_value_space(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str,
        analysis_population: str,
        claim_code: str | None = None,
        query: str | None = None,
        context_type: str | None = None,
        context_code: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        role: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        del role
        population = _m12c_population(analysis_population)
        stmt = (
            select(entities.Core3ClaimValueDimensionSummary)
            .where(entities.Core3ClaimValueDimensionSummary.project_id == self.project_id)
            .where(entities.Core3ClaimValueDimensionSummary.category_code == self.category_code)
            .where(entities.Core3ClaimValueDimensionSummary.batch_id == batch_id)
            .where(entities.Core3ClaimValueDimensionSummary.product_category == product_category.upper())
            .where(entities.Core3ClaimValueDimensionSummary.market_window == market_window)
            .where(entities.Core3ClaimValueDimensionSummary.analysis_population == population)
            .where(entities.Core3ClaimValueDimensionSummary.rule_version == CORE3_M12C_RULE_VERSION)
            .where(entities.Core3ClaimValueDimensionSummary.is_current.is_(True))
        )
        if claim_code:
            stmt = stmt.where(entities.Core3ClaimValueDimensionSummary.claim_code == claim_code)
        if context_type:
            stmt = stmt.where(entities.Core3ClaimValueDimensionSummary.dimension_type == context_type)
        if context_code:
            stmt = stmt.where(entities.Core3ClaimValueDimensionSummary.dimension_code == context_code)
        if size_tier:
            stmt = stmt.where(entities.Core3ClaimValueDimensionSummary.size_tier == size_tier)
        if price_band:
            stmt = stmt.where(entities.Core3ClaimValueDimensionSummary.price_band_group == price_band)
        stmt = _apply_m12c_query_filter(
            stmt,
            query=query,
            code_columns=(
                entities.Core3ClaimValueDimensionSummary.claim_code,
                entities.Core3ClaimValueDimensionSummary.dimension_code,
            ),
            name_columns=(
                entities.Core3ClaimValueDimensionSummary.claim_name,
                entities.Core3ClaimValueDimensionSummary.dimension_name,
            ),
        )
        stmt = stmt.order_by(
            entities.Core3ClaimValueDimensionSummary.premium_driver_sku_count.desc(),
            entities.Core3ClaimValueDimensionSummary.sales_driver_sku_count.desc(),
            entities.Core3ClaimValueDimensionSummary.estimated_avg_weekly_sales_amount.desc(),
            entities.Core3ClaimValueDimensionSummary.claim_code,
        )
        if limit != 0:
            stmt = stmt.limit(max(limit, 0))
        rows = list(self.db.execute(stmt).scalars())
        return {
            "market_window": market_window,
            "analysis_population": population,
            "filters": {
                "claim_code": claim_code,
                "query": query,
                "context_type": context_type,
                "context_code": context_code,
                "size_tier": size_tier,
                "price_band": price_band,
                "limit": limit,
            },
            "summary_count": len(rows),
            "items": [_claim_value_dimension_summary_payload(row) for row in rows],
            "method_note_cn": "卖点价值空间来自 M12C 维度汇总，用于观察某类卖点在市场池、用户任务、目标客群、价值战场中的可观测价值分布。",
        }

    def sku_claim_value(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        market_window: str,
        analysis_population: str,
        claim_code: str | None = None,
        query: str | None = None,
        context_type: str | None = None,
        context_code: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        role: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        population = _m12c_population(analysis_population)
        quant_rows = self._m12c_sku_claim_rows(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            market_window=market_window,
            analysis_population=population,
            claim_code=claim_code,
            query=query,
            context_type=context_type,
            context_code=context_code,
            size_tier=size_tier,
            price_band=price_band,
            role=role,
            limit=limit,
        )
        attr_rows = self._m12c_attribution_rows(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            market_window=market_window,
            analysis_population=population,
            context_type=context_type,
            context_code=context_code,
            size_tier=size_tier,
            price_band=price_band,
            limit=limit,
        )
        metric_by_id = self._m12c_metrics_by_id(row.metric_id for row in quant_rows)
        return {
            "sku_code": sku_code,
            "market_window": market_window,
            "analysis_population": population,
            "filters": {
                "claim_code": claim_code,
                "query": query,
                "context_type": context_type,
                "context_code": context_code,
                "size_tier": size_tier,
                "price_band": price_band,
                "role": role,
                "limit": limit,
            },
            "role_counts": _count_by([row.claim_value_role for row in quant_rows]),
            "claim_values": [_sku_claim_value_payload(row, metric_by_id.get(row.metric_id or "")) for row in quant_rows],
            "attributions": [_claim_attribution_payload(row) for row in attr_rows],
            "method_note_cn": "可比池卖点价格差异/销量差异是有卖点组与对照组的可观测差异；本品超额解释份额是对本品高于同池基准表现的解释性分摊，不代表单一卖点因果增量。",
        }

    def claim_contribution(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        market_window: str,
        analysis_population: str,
        context_type: str | None = None,
        context_code: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        population = _m12c_population(analysis_population)
        rows = self._m12c_attribution_rows(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            market_window=market_window,
            analysis_population=population,
            context_type=context_type,
            context_code=context_code,
            size_tier=size_tier,
            price_band=price_band,
            limit=limit,
        )
        return {
            "sku_code": sku_code,
            "market_window": market_window,
            "analysis_population": population,
            "filters": {
                "context_type": context_type,
                "context_code": context_code,
                "size_tier": size_tier,
                "price_band": price_band,
                "limit": limit,
            },
            "attribution_count": len(rows),
            "attributions": [_claim_attribution_payload(row) for row in rows],
            "method_note_cn": "SKU 归因把同一上下文中的正向卖点按可观测超额价格、销量和语义支撑权重分摊，用于解释哪些卖点更像成交支撑。",
        }

    def claim_opportunity_gaps(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        market_window: str,
        analysis_population: str,
        candidate_sku_code: str | None = None,
        context_type: str | None = None,
        context_code: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        population = _m12c_population(analysis_population)
        target_rows = self._m12c_sku_claim_rows(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            market_window=market_window,
            analysis_population=population,
            context_type=context_type,
            context_code=context_code,
            role=None,
            limit=0,
        )
        target_positive = {row.claim_code for row in target_rows if row.claim_value_role in M12C_POSITIVE_ROLES}
        target_gap_rows = [
            row
            for row in target_rows
            if row.claim_value_role in M12C_GAP_ROLES or (row.claim_value_role == "user_validated_need" and row.claim_code not in target_positive)
        ]
        candidate_advantages: list[Any] = []
        if candidate_sku_code:
            candidate_rows = self._m12c_sku_claim_rows(
                batch_id=batch_id,
                product_category=product_category,
                sku_code=candidate_sku_code,
                market_window=market_window,
                analysis_population=population,
                context_type=context_type,
                context_code=context_code,
                role=None,
                limit=0,
            )
            candidate_advantages = [
                row
                for row in candidate_rows
                if row.claim_value_role in M12C_POSITIVE_ROLES and row.claim_code not in target_positive
            ]
        target_gap_rows = _sort_m12c_claim_rows(target_gap_rows)[: max(limit, 0) if limit else None]
        candidate_advantages = _sort_m12c_claim_rows(candidate_advantages)[: max(limit, 0) if limit else None]
        metric_by_id = self._m12c_metrics_by_id([*(row.metric_id for row in target_gap_rows), *(row.metric_id for row in candidate_advantages)])
        return {
            "sku_code": sku_code,
            "candidate_sku_code": candidate_sku_code,
            "market_window": market_window,
            "analysis_population": population,
            "filters": {
                "context_type": context_type,
                "context_code": context_code,
                "limit": limit,
            },
            "target_opportunity_or_drag_claims": [_sku_claim_value_payload(row, metric_by_id.get(row.metric_id or "")) for row in target_gap_rows],
            "candidate_positive_claims_missing_on_target": [_sku_claim_value_payload(row, metric_by_id.get(row.metric_id or "")) for row in candidate_advantages],
            "method_note_cn": "机会缺口优先看本品机会/拖后腿卖点；如提供竞品，则补充竞品已形成正向贡献而本品未形成正向贡献的卖点。",
        }

    def claim_value_compare(
        self,
        *,
        batch_id: str,
        product_category: str,
        target_sku_code: str,
        candidate_sku_code: str,
        market_window: str,
        analysis_population: str,
        context_type: str | None = None,
        context_code: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        population = _m12c_population(analysis_population)
        target_rows = self._m12c_sku_claim_rows(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=target_sku_code,
            market_window=market_window,
            analysis_population=population,
            context_type=context_type,
            context_code=context_code,
            limit=0,
        )
        candidate_rows = self._m12c_sku_claim_rows(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=candidate_sku_code,
            market_window=market_window,
            analysis_population=population,
            context_type=context_type,
            context_code=context_code,
            limit=0,
        )
        target_best = _best_claim_row_by_code(target_rows)
        candidate_best = _best_claim_row_by_code(candidate_rows)
        all_codes = sorted(set(target_best) | set(candidate_best))
        paired = []
        target_advantage = []
        candidate_advantage = []
        shared_positive = []
        metric_by_id = self._m12c_metrics_by_id([*(row.metric_id for row in target_rows), *(row.metric_id for row in candidate_rows)])
        for claim_code in all_codes:
            target_row = target_best.get(claim_code)
            candidate_row = candidate_best.get(claim_code)
            item = {
                "claim_code": claim_code,
                "claim_name": (target_row.claim_name if target_row else None) or (candidate_row.claim_name if candidate_row else None),
                "target": _sku_claim_value_payload(target_row, metric_by_id.get(target_row.metric_id or "")) if target_row else {},
                "candidate": _sku_claim_value_payload(candidate_row, metric_by_id.get(candidate_row.metric_id or "")) if candidate_row else {},
                "relation": _claim_compare_relation(target_row, candidate_row),
            }
            paired.append(item)
            if item["relation"] == "shared_positive":
                shared_positive.append(item)
            elif item["relation"] == "target_advantage":
                target_advantage.append(item)
            elif item["relation"] == "candidate_advantage":
                candidate_advantage.append(item)
        paired = sorted(paired, key=_claim_compare_sort_key)[: max(limit, 0) if limit else None]
        return {
            "target_sku_code": target_sku_code,
            "candidate_sku_code": candidate_sku_code,
            "market_window": market_window,
            "analysis_population": population,
            "filters": {
                "context_type": context_type,
                "context_code": context_code,
                "limit": limit,
            },
            "shared_positive_claims": shared_positive[: max(limit, 0) if limit else None],
            "target_advantage_claims": target_advantage[: max(limit, 0) if limit else None],
            "candidate_advantage_claims": candidate_advantage[: max(limit, 0) if limit else None],
            "paired_claims": paired,
            "method_note_cn": "对比使用两款 SKU 各自在同类语义上下文中的 M12C 最强卖点角色，用于判断卖点层面的替代和差异压力。",
        }

    def _m12c_sku_claim_rows(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        market_window: str,
        analysis_population: str,
        claim_code: str | None = None,
        query: str | None = None,
        context_type: str | None = None,
        context_code: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        role: str | None = None,
        limit: int = 20,
    ) -> list[entities.Core3SkuClaimValueQuantification]:
        stmt = (
            select(entities.Core3SkuClaimValueQuantification)
            .where(entities.Core3SkuClaimValueQuantification.project_id == self.project_id)
            .where(entities.Core3SkuClaimValueQuantification.category_code == self.category_code)
            .where(entities.Core3SkuClaimValueQuantification.batch_id == batch_id)
            .where(entities.Core3SkuClaimValueQuantification.product_category == product_category.upper())
            .where(entities.Core3SkuClaimValueQuantification.market_window == market_window)
            .where(entities.Core3SkuClaimValueQuantification.analysis_population == analysis_population)
            .where(entities.Core3SkuClaimValueQuantification.sku_code == sku_code)
            .where(entities.Core3SkuClaimValueQuantification.rule_version == CORE3_M12C_RULE_VERSION)
            .where(entities.Core3SkuClaimValueQuantification.is_current.is_(True))
        )
        if claim_code:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.claim_code == claim_code)
        if context_type:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.context_type == context_type)
        if context_code:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.context_code == context_code)
        if size_tier:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.size_tier == size_tier)
        if price_band:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.price_band_group == price_band)
        if role:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.claim_value_role == role)
        stmt = _apply_m12c_query_filter(
            stmt,
            query=query,
            code_columns=(
                entities.Core3SkuClaimValueQuantification.claim_code,
                entities.Core3SkuClaimValueQuantification.context_code,
            ),
            name_columns=(
                entities.Core3SkuClaimValueQuantification.claim_name,
                entities.Core3SkuClaimValueQuantification.context_name,
            ),
        )
        rows = _sort_m12c_claim_rows(list(self.db.execute(stmt).scalars()))
        return rows[: max(limit, 0)] if limit else rows

    def _m12c_metrics_by_id(self, metric_ids: Sequence[str | None]) -> dict[str, entities.Core3ClaimValuePoolMetric]:
        ids = sorted({str(metric_id) for metric_id in metric_ids if metric_id})
        if not ids:
            return {}
        stmt = select(entities.Core3ClaimValuePoolMetric).where(entities.Core3ClaimValuePoolMetric.metric_id.in_(ids))
        return {row.metric_id: row for row in self.db.execute(stmt).scalars()}

    def _m12c_attribution_rows(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        market_window: str,
        analysis_population: str,
        context_type: str | None = None,
        context_code: str | None = None,
        size_tier: str | None = None,
        price_band: str | None = None,
        limit: int = 20,
    ) -> list[entities.Core3SkuClaimContributionAttribution]:
        stmt = (
            select(entities.Core3SkuClaimContributionAttribution)
            .where(entities.Core3SkuClaimContributionAttribution.project_id == self.project_id)
            .where(entities.Core3SkuClaimContributionAttribution.category_code == self.category_code)
            .where(entities.Core3SkuClaimContributionAttribution.batch_id == batch_id)
            .where(entities.Core3SkuClaimContributionAttribution.product_category == product_category.upper())
            .where(entities.Core3SkuClaimContributionAttribution.market_window == market_window)
            .where(entities.Core3SkuClaimContributionAttribution.analysis_population == analysis_population)
            .where(entities.Core3SkuClaimContributionAttribution.sku_code == sku_code)
            .where(entities.Core3SkuClaimContributionAttribution.rule_version == CORE3_M12C_RULE_VERSION)
            .where(entities.Core3SkuClaimContributionAttribution.is_current.is_(True))
        )
        if context_type:
            stmt = stmt.where(entities.Core3SkuClaimContributionAttribution.context_type == context_type)
        if context_code:
            stmt = stmt.where(entities.Core3SkuClaimContributionAttribution.context_code == context_code)
        if size_tier:
            stmt = stmt.where(entities.Core3SkuClaimContributionAttribution.size_tier == size_tier)
        if price_band:
            stmt = stmt.where(entities.Core3SkuClaimContributionAttribution.price_band_group == price_band)
        stmt = stmt.order_by(
            entities.Core3SkuClaimContributionAttribution.sku_weekly_sales_amount_lift_abs.desc(),
            entities.Core3SkuClaimContributionAttribution.sku_price_premium_abs.desc(),
            entities.Core3SkuClaimContributionAttribution.confidence.desc(),
        )
        if limit != 0:
            stmt = stmt.limit(max(limit, 0))
        return list(self.db.execute(stmt).scalars())

    def _sales_overlap_market_fallback(
        self,
        *,
        batch_id: str,
        target_sku_code: str,
        candidate_sku_code: str,
        market_window: str,
    ) -> dict[str, Any]:
        target_market = self._market_profile(batch_id=batch_id, sku_code=target_sku_code, market_window=market_window)
        candidate_market = self._market_profile(batch_id=batch_id, sku_code=candidate_sku_code, market_window=market_window)
        target_avg_volume = _safe_avg(_decimal(target_market.sales_volume_total) if target_market else None, target_market.active_week_count if target_market else None)
        candidate_avg_volume = _safe_avg(
            _decimal(candidate_market.sales_volume_total) if candidate_market else None,
            candidate_market.active_week_count if candidate_market else None,
        )
        target_avg_amount = _safe_avg(_decimal(target_market.sales_amount_total) if target_market else None, target_market.active_week_count if target_market else None)
        candidate_avg_amount = _safe_avg(
            _decimal(candidate_market.sales_amount_total) if candidate_market else None,
            candidate_market.active_week_count if candidate_market else None,
        )
        return {
            "method": "market_profile_active_week_average_fallback",
            "policy_note_cn": "未找到两款 SKU 的 M01 周度明细重叠，退回 M07 活跃周均；不能作为精确重叠周判断。",
            "target_sku_code": target_sku_code,
            "candidate_sku_code": candidate_sku_code,
            "overlap_weeks": [],
            "overlap_week_count": 0,
            "target": _sales_market_fallback_side(target_market, target_avg_volume, target_avg_amount),
            "candidate": _sales_market_fallback_side(candidate_market, candidate_avg_volume, candidate_avg_amount),
            "comparison": _sales_comparison(target_avg_volume, candidate_avg_volume, target_avg_amount, candidate_avg_amount),
        }

    def _market_weekly_rows(self, *, batch_id: str, sku_codes: Sequence[str]) -> list[entities.Core3CleanMarketWeekly]:
        stmt = (
            select(entities.Core3CleanMarketWeekly)
            .where(entities.Core3CleanMarketWeekly.project_id == self.project_id)
            .where(entities.Core3CleanMarketWeekly.category_code == self.category_code)
            .where(entities.Core3CleanMarketWeekly.batch_id == batch_id)
            .where(entities.Core3CleanMarketWeekly.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3CleanMarketWeekly.period_week_index.is_not(None))
            .where(entities.Core3CleanMarketWeekly.record_status == "active")
            .where(entities.Core3CleanMarketWeekly.quality_status == "ok")
            .order_by(entities.Core3CleanMarketWeekly.sku_code, entities.Core3CleanMarketWeekly.period_week_index)
        )
        return list(self.db.execute(stmt).scalars())

    def _semantic_summaries_by_codes(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
        dimension_type: str,
        dimension_codes: Sequence[str],
    ) -> list[entities.Core3SemanticMarketDimensionSummary]:
        if not dimension_codes:
            return []
        stmt = (
            select(entities.Core3SemanticMarketDimensionSummary)
            .where(entities.Core3SemanticMarketDimensionSummary.project_id == self.project_id)
            .where(entities.Core3SemanticMarketDimensionSummary.category_code == self.category_code)
            .where(entities.Core3SemanticMarketDimensionSummary.batch_id == batch_id)
            .where(entities.Core3SemanticMarketDimensionSummary.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketDimensionSummary.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketDimensionSummary.market_window == market_window)
            .where(entities.Core3SemanticMarketDimensionSummary.dimension_type == dimension_type)
            .where(entities.Core3SemanticMarketDimensionSummary.dimension_code.in_(tuple(dimension_codes)))
            .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
        )
        return list(self.db.execute(stmt).scalars())

    def _semantic_dimension_positions(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        analysis_population: str,
        market_window: str,
        allocations: Sequence[entities.Core3SemanticMarketAllocation],
        user_task_profile: entities.Core3M09cSkuUserTaskProfile | None = None,
        target_group_profile: entities.Core3M10cSkuTargetGroupProfile | None = None,
        battlefield_profile: entities.Core3SkuValueBattlefieldProfile | None = None,
    ) -> list[dict[str, Any]]:
        if product_category != "TV":
            return []
        codes_by_type: dict[str, list[str]] = {}
        for allocation in allocations:
            codes_by_type.setdefault(allocation.dimension_type, [])
            if allocation.dimension_code not in codes_by_type[allocation.dimension_type]:
                codes_by_type[allocation.dimension_type].append(allocation.dimension_code)
        _add_profile_dimension_codes(codes_by_type, user_task_profile, target_group_profile, battlefield_profile)
        if not codes_by_type:
            return []

        summary_by_key: dict[tuple[str, str], entities.Core3SemanticMarketDimensionSummary] = {}
        for dimension_type, dimension_codes in codes_by_type.items():
            for row in self._semantic_summaries_by_codes(
                batch_id=batch_id,
                product_category=product_category,
                analysis_population=analysis_population,
                market_window=market_window,
                dimension_type=dimension_type,
                dimension_codes=dimension_codes,
            ):
                summary_by_key[(row.dimension_type, row.dimension_code)] = row

        allocation_by_key = {(row.dimension_type, row.dimension_code): row for row in allocations}
        contribution_by_key = self._semantic_contribution_by_dimension(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            analysis_population=analysis_population,
            market_window=market_window,
            dimension_codes=[code for dimension_codes in codes_by_type.values() for code in dimension_codes],
        )
        positions: list[dict[str, Any]] = []
        for dimension_type, dimension_codes in codes_by_type.items():
            for dimension_code in dimension_codes:
                key = (dimension_type, dimension_code)
                allocation = allocation_by_key.get(key)
                summary = summary_by_key.get(key)
                contribution = contribution_by_key.get(key)
                dimension_name = ""
                if allocation:
                    dimension_name = allocation.dimension_name
                elif summary:
                    dimension_name = summary.dimension_name
                else:
                    dimension_name = dimension_code
                positions.append(
                    {
                        "dimension_type": dimension_type,
                        "dimension_code": dimension_code,
                        "dimension_name": dimension_name,
                        "market_space": _semantic_summary_payload(summary) if summary else {},
                        "sku_allocation": _allocation_payload(allocation) if allocation else {},
                        "sku_contribution": _semantic_contribution_payload(contribution) if contribution else {},
                    }
                )
        return positions

    def _semantic_contribution_by_dimension(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        analysis_population: str,
        market_window: str,
        dimension_codes: Sequence[str],
    ) -> dict[tuple[str, str], entities.Core3SemanticMarketSkuContribution]:
        if not dimension_codes:
            return {}
        stmt = (
            select(entities.Core3SemanticMarketSkuContribution)
            .where(entities.Core3SemanticMarketSkuContribution.project_id == self.project_id)
            .where(entities.Core3SemanticMarketSkuContribution.category_code == self.category_code)
            .where(entities.Core3SemanticMarketSkuContribution.batch_id == batch_id)
            .where(entities.Core3SemanticMarketSkuContribution.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketSkuContribution.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketSkuContribution.market_window == market_window)
            .where(entities.Core3SemanticMarketSkuContribution.sku_code == sku_code)
            .where(entities.Core3SemanticMarketSkuContribution.dimension_code.in_(tuple(dimension_codes)))
            .where(entities.Core3SemanticMarketSkuContribution.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketSkuContribution.is_current.is_(True))
        )
        return {(row.dimension_type, row.dimension_code): row for row in self.db.execute(stmt).scalars()}

    def _market_pool_summary(
        self,
        *,
        batch_id: str,
        market: entities.Core3SkuMarketProfile | None,
        product_category: str,
        market_window: str,
        size_tier: str | None,
    ) -> dict[str, Any]:
        if market is None or not market.price_band_size:
            return {}
        target_size_tier = size_tier or market.size_segment
        if not target_size_tier:
            return {}
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .where(entities.Core3SkuMarketProfile.price_band_size == market.price_band_size)
        )
        if not size_tier:
            stmt = stmt.where(entities.Core3SkuMarketProfile.size_segment == target_size_tier)
        rows = list(self.db.execute(stmt).scalars())
        if size_tier and rows:
            params_by_sku = self._param_profiles_by_sku(
                batch_id=batch_id,
                product_category=product_category,
                sku_codes=[row.sku_code for row in rows],
            )
            rows = [
                row
                for row in rows
                if _param_size_tier(params_by_sku.get(row.sku_code)) == target_size_tier
                or (row.size_segment == target_size_tier and row.sku_code not in params_by_sku)
            ]
        if not rows:
            return {}
        target_avg = _safe_avg(_decimal(market.sales_volume_total), market.active_week_count) or Decimal("0")
        total_sales_volume = sum((_decimal(row.sales_volume_total) or Decimal("0")) for row in rows)
        total_sales_amount = sum((_decimal(row.sales_amount_total) or Decimal("0")) for row in rows)
        total_avg_weekly = sum((_safe_avg(_decimal(row.sales_volume_total), row.active_week_count) or Decimal("0")) for row in rows)
        rank = 1 + sum(
            1
            for row in rows
            if (_safe_avg(_decimal(row.sales_volume_total), row.active_week_count) or Decimal("0")) > target_avg
        )
        target_sales_volume = _decimal(market.sales_volume_total) or Decimal("0")
        target_sales_amount = _decimal(market.sales_amount_total) or Decimal("0")
        return {
            "size_tier": target_size_tier,
            "market_size_tier": market.size_segment,
            "price_band_in_size_tier": market.price_band_size,
            "sku_count": len(rows),
            "total_sales_volume": _number(total_sales_volume),
            "total_sales_amount": _number(total_sales_amount),
            "total_avg_weekly_sales_volume": _number(total_avg_weekly),
            "target_rank_by_avg_weekly_sales": rank,
            "target_sales_volume": _number(target_sales_volume),
            "target_avg_weekly_sales_volume": _number(target_avg),
            "target_sales_volume_share": _number(target_sales_volume / total_sales_volume) if total_sales_volume else None,
            "target_sales_amount_share": _number(target_sales_amount / total_sales_amount) if total_sales_amount else None,
        }

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

    def _param_profiles_by_sku(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_codes: Sequence[str],
    ) -> dict[str, entities.Core3SkuParamProfile]:
        if not sku_codes:
            return {}
        rule_version = CORE3_M03B_AC_RULE_VERSION if product_category == "AC" else CORE3_M03B_RULE_VERSION
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
        )
        return {row.sku_code: row for row in self.db.execute(stmt).scalars()}

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
        for match in MODEL_TOKEN_RE.finditer(_strip_brand_words(text)):
            token = " ".join(match.group(0).strip().split())
            if token and token.lower() not in {"sku", "pro", "max", "mini", "plus"}:
                return token
        return text

    @staticmethod
    def _normalize_requested_model(value: str | None) -> str | None:
        text = _strip_brand_words(value or "")
        if not text:
            return None
        for match in MODEL_TOKEN_RE.finditer(text):
            token = " ".join(match.group(0).strip().split())
            if token:
                return token.upper()
        return text.strip().upper()

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


def _strip_brand_words(value: str) -> str:
    text = str(value or "")
    for word in BRAND_QUERY_WORDS:
        text = re.sub(re.escape(word), " ", text, flags=re.IGNORECASE)
    return " ".join(text.strip().split())


def _exact_model_rows(rows: Sequence[Any], requested_model: str) -> list[Any]:
    requested_key = _model_key(requested_model)
    if not requested_key:
        return []
    return [row for row in rows if _model_key(getattr(row, "model_name", None)) == requested_key]


def _rank_model_rows(rows: Sequence[Any], requested_model: str) -> list[Any]:
    ranked = [
        (_model_match_rank(getattr(row, "model_name", None), requested_model), str(getattr(row, "sku_code", "")), row)
        for row in rows
    ]
    exact_rows = [row for rank, _sku_code, row in ranked if rank == 0]
    if exact_rows:
        return sorted(exact_rows, key=lambda row: str(getattr(row, "sku_code", "")))
    return [row for rank, _sku_code, row in sorted(ranked, key=lambda item: (item[0], item[1])) if rank < 100]


def _model_query_variants(requested_model: str) -> list[str]:
    variants = [requested_model]
    compact_key = _model_key(requested_model)
    if re.match(r"^\d{3}[A-Z]", compact_key):
        size_candidate = int(compact_key[:2])
        if 24 <= size_candidate <= 99:
            corrected = f"{compact_key[:2]}{compact_key[3:]}"
            if corrected and corrected not in {_model_key(item) for item in variants}:
                variants.append(corrected)
    return variants


def _model_match_rank(model_name: Any, requested_model: str) -> int:
    model_key = _model_key(model_name)
    requested_key = _model_key(requested_model)
    if not model_key or not requested_key:
        return 100
    if model_key == requested_key:
        return 0

    requested_has_pro = _has_suffix(requested_key, "PRO")
    model_has_pro = _has_suffix(model_key, "PRO")
    if requested_has_pro and not model_has_pro:
        return 100
    if not requested_has_pro and model_has_pro and model_key.startswith(requested_key):
        return 30 + min(len(model_key) - len(requested_key), 20)
    if model_key.startswith(requested_key):
        return 10 + min(len(model_key) - len(requested_key), 20)
    if requested_key in model_key:
        return 20 + min(len(model_key) - len(requested_key), 20)
    if requested_key.startswith(model_key):
        return 60 + min(len(requested_key) - len(model_key), 20)
    return 100


def _model_key(value: Any) -> str:
    text = _strip_brand_words(str(value or "")).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def _model_like_anchor(value: str) -> str:
    text = _strip_brand_words(value).upper()
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[\s-]*(PRO|PLUS|MAX|MINI|\+)$", "", text, flags=re.IGNORECASE).strip()
    return text or value


def _has_suffix(model_key: str, suffix: str) -> bool:
    return model_key.endswith(suffix)


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


def _param_size_tier(row: entities.Core3SkuParamProfile | None) -> str | None:
    if row is None:
        return None
    values = row.param_values_json or {}
    tiers = values.get("dimension_tier_profile") or {}
    size_tier = tiers.get("size") if isinstance(tiers, dict) else None
    return str(size_tier) if size_tier else None


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


def _add_profile_dimension_codes(
    codes_by_type: dict[str, list[str]],
    user_task_profile: entities.Core3M09cSkuUserTaskProfile | None,
    target_group_profile: entities.Core3M10cSkuTargetGroupProfile | None,
    battlefield_profile: entities.Core3SkuValueBattlefieldProfile | None,
) -> None:
    if user_task_profile:
        _append_dimension_codes(
            codes_by_type,
            "user_task",
            [
                user_task_profile.primary_user_task_code,
                *(user_task_profile.secondary_user_task_codes_json or []),
                *(user_task_profile.comment_observed_task_codes_json or []),
                *(user_task_profile.brand_claimed_task_codes_json or []),
                *(user_task_profile.latent_capability_task_codes_json or []),
                *(user_task_profile.drag_factor_task_codes_json or []),
            ],
        )
    if target_group_profile:
        _append_dimension_codes(
            codes_by_type,
            "target_group",
            [
                target_group_profile.primary_target_group_code,
                *(target_group_profile.secondary_target_group_codes_json or []),
                *(target_group_profile.comment_observed_group_codes_json or []),
                *(target_group_profile.brand_claimed_group_codes_json or []),
                *(target_group_profile.latent_group_codes_json or []),
                *(target_group_profile.unmet_group_need_codes_json or []),
            ],
        )
    if battlefield_profile:
        _append_dimension_codes(
            codes_by_type,
            "battlefield",
            [
                battlefield_profile.primary_battlefield_code,
                *(battlefield_profile.secondary_battlefield_codes_json or []),
                *(battlefield_profile.opportunity_battlefield_codes_json or []),
                *(battlefield_profile.drag_factor_battlefield_codes_json or []),
            ],
        )


def _append_dimension_codes(codes_by_type: dict[str, list[str]], dimension_type: str, codes: Sequence[Any]) -> None:
    values = codes_by_type.setdefault(dimension_type, [])
    for code in codes:
        text = str(code or "").strip()
        if text and text not in values:
            values.append(text)


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


def _claim_value_dimension_summary_payload(row: entities.Core3ClaimValueDimensionSummary) -> dict[str, Any]:
    return {
        "claim_code": row.claim_code,
        "claim_name": row.claim_name,
        "dimension_type": row.dimension_type,
        "dimension_code": row.dimension_code,
        "dimension_name": row.dimension_name,
        "size_tier": row.size_tier,
        "price_band_group": row.price_band_group,
        "sku_count": row.sku_count,
        "role_counts": {
            "premium_driver_estimated": row.premium_driver_sku_count,
            "sales_driver_estimated": row.sales_driver_sku_count,
            "basic_threshold": row.basic_threshold_sku_count,
            "brand_claim_only": row.brand_claim_only_sku_count,
            "drag_factor": row.drag_factor_sku_count,
            "opportunity_gap": row.opportunity_gap_sku_count,
        },
        "market_space": {
            "estimated_sales_volume": _number(row.estimated_sales_volume),
            "estimated_avg_weekly_sales_volume": _number(row.estimated_avg_weekly_sales_volume),
            "estimated_sales_amount": _number(row.estimated_sales_amount),
            "estimated_avg_weekly_sales_amount": _number(row.estimated_avg_weekly_sales_amount),
        },
        "top_skus": row.top_skus_json or [],
        "business_summary_cn": row.business_summary_cn,
    }


def _sku_claim_value_payload(
    row: entities.Core3SkuClaimValueQuantification | None,
    metric: entities.Core3ClaimValuePoolMetric | None = None,
) -> dict[str, Any]:
    if row is None:
        return {}
    pool_price_delta = _number(metric.price_premium_abs) if metric else None
    pool_sales_delta = _number(metric.weekly_sales_lift_abs) if metric else None
    pool_amount_delta = _number(metric.weekly_sales_amount_lift_abs) if metric else None
    sku_price_share = _number(row.estimated_price_premium_abs)
    sku_sales_share = _number(row.estimated_weekly_sales_lift_abs)
    sku_amount_share = _number(row.estimated_weekly_sales_amount_lift_abs)
    business_label = _m12c_business_value_label(row.claim_value_role, pool_price_delta)
    business_meaning = _m12c_business_value_meaning_cn(row.claim_value_role, pool_price_delta)
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "claim_code": row.claim_code,
        "claim_name": row.claim_name,
        "claim_dimension": row.claim_dimension,
        "claim_value_role": row.claim_value_role,
        "business_value_label": business_label,
        "business_value_meaning_cn": business_meaning,
        "context_type": row.context_type,
        "context_code": row.context_code,
        "context_name": row.context_name,
        "size_tier": row.size_tier,
        "price_band_group": row.price_band_group,
        "pool_effect": {
            "pool_claim_price_delta_abs": pool_price_delta,
            "pool_claim_weekly_sales_delta_abs": pool_sales_delta,
            "pool_claim_weekly_sales_amount_delta_abs": pool_amount_delta,
            "with_claim_sku_count": getattr(metric, "with_claim_sku_count", None) if metric else None,
            "without_claim_sku_count": getattr(metric, "without_claim_sku_count", None) if metric else None,
            "effect_confidence": _number(metric.effect_confidence) if metric else None,
        },
        "sku_excess_explanation": {
            "sku_excess_price_explained_abs": sku_price_share,
            "sku_excess_weekly_sales_explained_abs": sku_sales_share,
            "sku_excess_weekly_sales_amount_explained_abs": sku_amount_share,
            "contribution_share_in_sku": _number(row.contribution_share_in_sku),
        },
        "evidence_strength": {
            "claim": _number(row.claim_evidence_strength),
            "param": _number(row.param_support_strength),
            "comment": _number(row.comment_support_strength),
            "semantic": _number(row.semantic_support_strength),
        },
        "estimated_contribution": {
            "price_premium_abs": sku_price_share,
            "weekly_sales_lift_abs": sku_sales_share,
            "weekly_sales_amount_lift_abs": sku_amount_share,
            "contribution_share_in_sku": _number(row.contribution_share_in_sku),
        },
        "attribution_confidence": _number(row.attribution_confidence),
        "supporting_dimensions": row.supporting_dimensions_json or {},
        "reason_cn": row.reason_cn,
        "quality_flags": row.quality_flags_json or [],
        "evidence_id_count": len(row.evidence_ids_json or []),
    }


def _claim_attribution_payload(row: entities.Core3SkuClaimContributionAttribution) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "context_type": row.context_type,
        "context_code": row.context_code,
        "context_name": row.context_name,
        "size_tier": row.size_tier,
        "price_band_group": row.price_band_group,
        "baseline": {
            "price": _number(row.baseline_price),
            "weekly_sales_volume": _number(row.baseline_weekly_sales_volume),
            "weekly_sales_amount": _number(row.baseline_weekly_sales_amount),
        },
        "sku_observed": {
            "price": _number(row.sku_price),
            "weekly_sales_volume": _number(row.sku_weekly_sales_volume),
            "weekly_sales_amount": _number(row.sku_weekly_sales_amount),
        },
        "sku_gap_vs_baseline": {
            "price_premium_abs": _number(row.sku_price_premium_abs),
            "weekly_sales_lift_abs": _number(row.sku_weekly_sales_lift_abs),
            "weekly_sales_amount_lift_abs": _number(row.sku_weekly_sales_amount_lift_abs),
        },
        "positive_claims": row.positive_claims_json or [],
        "drag_claims": row.drag_claims_json or [],
        "opportunity_claims": row.opportunity_claims_json or [],
        "attribution_summary_cn": row.attribution_summary_cn,
        "confidence": _number(row.confidence),
    }


def _m12c_business_value_label(role: str | None, pool_price_delta: Any = None) -> str:
    price_delta = _decimal(pool_price_delta) or Decimal("0")
    role = str(role or "")
    if role == M12C_ROLE_PREMIUM:
        return "强溢价卖点" if price_delta > 0 else "组合型增值卖点"
    if role == M12C_ROLE_SALES:
        return "强销量卖点"
    if role == M12C_ROLE_BASIC:
        return "基础门槛卖点"
    if role == M12C_ROLE_VALUE_BUNDLE:
        return "组合型增值卖点"
    if role == M12C_ROLE_WEAK_USER:
        return "用户感知不足卖点"
    if role == M12C_ROLE_HIGH_PRICE_INTERCEPT:
        return "高价竞品拦截卖点"
    if role == M12C_ROLE_PRICE_UP:
        return "价格上探机会卖点"
    if role == M12C_ROLE_DRAG:
        return "拖后腿卖点"
    if role == M12C_ROLE_OPPORTUNITY:
        return "机会缺口"
    if role == M12C_ROLE_BRAND:
        return "厂家主张卖点"
    if role == M12C_ROLE_USER_NEED:
        return "用户验证需求"
    return "样本不足"


def _m12c_business_value_meaning_cn(role: str | None, pool_price_delta: Any = None) -> str:
    price_delta = _decimal(pool_price_delta) or Decimal("0")
    role = str(role or "")
    if role == M12C_ROLE_PREMIUM and price_delta > 0:
        return "同尺寸、同价格带、同语义市场中，有该卖点且证据成立的一组 SKU 价格更高。"
    if role == M12C_ROLE_SALES:
        return "价格不一定更高，但更能解释同池周均销量或销额优势。"
    if role == M12C_ROLE_BASIC:
        return "同池普遍具备，有了不加价，缺了会掉队。"
    if role == M12C_ROLE_VALUE_BUNDLE or (role == M12C_ROLE_PREMIUM and price_delta <= 0):
        return "单点不一定独立溢价，但与一组高价值卖点组合后参与高端价值解释。"
    if role == M12C_ROLE_WEAK_USER:
        return "参数或卖点存在，但评论验证弱、负向明显，或弱于高价竞品。"
    if role == M12C_ROLE_HIGH_PRICE_INTERCEPT:
        return "同池高价竞品具备并能成交，本品缺失、表达弱或评论弱。"
    if role == M12C_ROLE_PRICE_UP:
        return "高价 SKU 反复具备且有市场价值，本品补强后可能提升上探空间。"
    if role == M12C_ROLE_DRAG:
        return "厂家主张、参数或评论之间不一致，削弱关键战场、任务或客群。"
    if role == M12C_ROLE_OPPORTUNITY:
        return "同池强竞品或高价值 SKU 具备，本品缺失或表达弱。"
    if role == M12C_ROLE_BRAND:
        return "卖点文本存在，但参数、评论或市场验证不足。"
    if role == M12C_ROLE_USER_NEED:
        return "评论中存在需求，但本品卖点或参数支撑不足。"
    return "可比池、对照组或评论样本不足，不能稳定判断。"


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


def _m12c_population(analysis_population: str) -> str:
    if analysis_population == "fact_complete_with_comment":
        return "claim_value_ready_with_comment"
    if analysis_population == "all_semantic_profiles":
        return "claim_value_ready"
    return analysis_population


def _apply_m12c_query_filter(stmt: Any, *, query: str | None, code_columns: Sequence[Any], name_columns: Sequence[Any]) -> Any:
    terms = _query_terms(query)
    if not terms:
        return stmt
    filters = []
    for term in terms:
        like_value = f"%{_escape_like(term.lower())}%"
        filters.extend(func.lower(column).like(like_value, escape="\\") for column in (*code_columns, *name_columns))
    return stmt.where(or_(*filters)) if filters else stmt


def _sort_m12c_claim_rows(rows: Sequence[entities.Core3SkuClaimValueQuantification]) -> list[entities.Core3SkuClaimValueQuantification]:
    return sorted(
        rows,
        key=lambda row: (
            M12C_ROLE_PRIORITY.get(row.claim_value_role, 99),
            -float(_decimal(row.estimated_weekly_sales_amount_lift_abs) or Decimal("0")),
            -float(_decimal(row.estimated_price_premium_abs) or Decimal("0")),
            -float(_decimal(row.attribution_confidence) or Decimal("0")),
            row.claim_code,
        ),
    )


def _best_claim_row_by_code(rows: Sequence[entities.Core3SkuClaimValueQuantification]) -> dict[str, entities.Core3SkuClaimValueQuantification]:
    result: dict[str, entities.Core3SkuClaimValueQuantification] = {}
    for row in _sort_m12c_claim_rows(rows):
        result.setdefault(row.claim_code, row)
    return result


def _claim_compare_relation(
    target_row: entities.Core3SkuClaimValueQuantification | None,
    candidate_row: entities.Core3SkuClaimValueQuantification | None,
) -> str:
    target_positive = bool(target_row and target_row.claim_value_role in M12C_POSITIVE_ROLES)
    candidate_positive = bool(candidate_row and candidate_row.claim_value_role in M12C_POSITIVE_ROLES)
    if target_positive and candidate_positive:
        return "shared_positive"
    if target_positive:
        return "target_advantage"
    if candidate_positive:
        return "candidate_advantage"
    if target_row and target_row.claim_value_role == "drag_factor":
        return "target_drag"
    if candidate_row and candidate_row.claim_value_role == "drag_factor":
        return "candidate_drag"
    return "other"


def _claim_compare_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    relation_order = {
        "shared_positive": 0,
        "target_advantage": 1,
        "candidate_advantage": 2,
        "target_drag": 3,
        "candidate_drag": 4,
        "other": 5,
    }
    target_amount = (((item.get("target") or {}).get("estimated_contribution") or {}).get("weekly_sales_amount_lift_abs")) or 0
    candidate_amount = (((item.get("candidate") or {}).get("estimated_contribution") or {}).get("weekly_sales_amount_lift_abs")) or 0
    return (relation_order.get(str(item.get("relation")), 99), -max(float(target_amount or 0), float(candidate_amount or 0)), str(item.get("claim_code") or ""))


def _count_by(values: Sequence[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result


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


def _avg_decimal(values: Sequence[Decimal | None]) -> Decimal | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present, Decimal("0")) / Decimal(len(present))


def _safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator in (None, Decimal("0")):
        return None
    return numerator / denominator


def _candidate_market_payload(
    row: entities.Core3SkuMarketProfile,
    *,
    target_market: entities.Core3SkuMarketProfile,
) -> dict[str, Any]:
    price = _decimal(row.price_wavg)
    target_price = _decimal(target_market.price_wavg)
    price_gap = price - target_price if price is not None and target_price is not None else None
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "screen_size_inch": _number(row.screen_size_inch),
        "size_tier": row.size_segment,
        "price_band_in_size_tier": row.price_band_size,
        "price_wavg": _number(row.price_wavg),
        "sales_volume_total": _number(row.sales_volume_total),
        "avg_weekly_sales_volume": _number(_safe_avg(_decimal(row.sales_volume_total), row.active_week_count)),
        "same_pool_sku_count": row.same_pool_sku_count,
        "price_gap_to_target": _number(price_gap),
        "price_gap_pct_to_target": _number(_safe_ratio(price_gap, target_price)),
        "evidence_id_count": len(row.evidence_ids or []),
    }


def _candidate_pool_sort_key(
    row: entities.Core3SkuMarketProfile,
    target_market: entities.Core3SkuMarketProfile,
) -> tuple[int, int, Decimal, Decimal, str]:
    row_size = _decimal(row.screen_size_inch)
    target_size = _decimal(target_market.screen_size_inch)
    exact_size_rank = 0 if row_size is not None and target_size is not None and abs(row_size - target_size) <= Decimal("0.5") else 1
    band_distance = _price_band_distance(row.price_band_size, target_market.price_band_size)
    price_gap = abs((_decimal(row.price_wavg) or Decimal("0")) - (_decimal(target_market.price_wavg) or Decimal("0")))
    sales = _decimal(row.sales_volume_total) or Decimal("0")
    return (exact_size_rank, band_distance, price_gap, -sales, row.sku_code)


def _price_band_distance(left: Any, right: Any) -> int:
    order = {"low": 0, "mid_low": 1, "mid": 2, "mid_high": 3, "high": 4}
    left_key = str(left or "").lower()
    right_key = str(right or "").lower()
    if left_key not in order or right_key not in order:
        return 99
    return abs(order[left_key] - order[right_key])


def _weekly_market_by_sku(rows: Sequence[entities.Core3CleanMarketWeekly]) -> dict[str, dict[int, dict[str, Any]]]:
    grouped: dict[str, dict[int, dict[str, Any]]] = {}
    for row in rows:
        if not row.sku_code or row.period_week_index is None:
            continue
        sku_weeks = grouped.setdefault(row.sku_code, {})
        bucket = sku_weeks.setdefault(
            row.period_week_index,
            {
                "period_week_index": row.period_week_index,
                "period_raw": row.period_raw,
                "sales_volume": Decimal("0"),
                "sales_amount": Decimal("0"),
                "platforms": set(),
                "row_count": 0,
            },
        )
        bucket["sales_volume"] += _decimal(row.sales_volume) or Decimal("0")
        bucket["sales_amount"] += _decimal(row.sales_amount) or Decimal("0")
        if row.platform_type:
            bucket["platforms"].add(row.platform_type)
        bucket["row_count"] += 1
    for sku_weeks in grouped.values():
        for bucket in sku_weeks.values():
            volume = bucket["sales_volume"]
            amount = bucket["sales_amount"]
            bucket["avg_price"] = _safe_ratio(amount, volume)
            bucket["platforms"] = sorted(bucket["platforms"])
    return grouped


def _sales_overlap_side(
    sku_code: str,
    weekly_values: Sequence[dict[str, Any]],
    avg_volume: Decimal | None,
    avg_amount: Decimal | None,
) -> dict[str, Any]:
    total_volume = sum((_decimal(item.get("sales_volume")) or Decimal("0")) for item in weekly_values)
    total_amount = sum((_decimal(item.get("sales_amount")) or Decimal("0")) for item in weekly_values)
    return {
        "sku_code": sku_code,
        "overlap_sales_volume": _number(total_volume),
        "overlap_sales_amount": _number(total_amount),
        "avg_weekly_sales_volume_on_overlap_weeks": _number(avg_volume),
        "avg_weekly_sales_amount_on_overlap_weeks": _number(avg_amount),
        "avg_price_on_overlap_weeks": _number(_safe_ratio(total_amount, total_volume)),
        "weekly_points": [
            {
                "period_week_index": item["period_week_index"],
                "period_raw": item.get("period_raw"),
                "sales_volume": _number(item.get("sales_volume")),
                "sales_amount": _number(item.get("sales_amount")),
                "avg_price": _number(item.get("avg_price")),
                "platforms": item.get("platforms") or [],
                "row_count": item.get("row_count"),
            }
            for item in weekly_values
        ],
    }


def _sales_market_fallback_side(
    row: entities.Core3SkuMarketProfile | None,
    avg_volume: Decimal | None,
    avg_amount: Decimal | None,
) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "sku_code": row.sku_code,
        "sales_volume_total": _number(row.sales_volume_total),
        "sales_amount_total": _number(row.sales_amount_total),
        "active_week_count": row.active_week_count,
        "avg_weekly_sales_volume": _number(avg_volume),
        "avg_weekly_sales_amount": _number(avg_amount),
        "price_wavg": _number(row.price_wavg),
    }


def _sales_comparison(
    target_avg_volume: Decimal | None,
    candidate_avg_volume: Decimal | None,
    target_avg_amount: Decimal | None,
    candidate_avg_amount: Decimal | None,
) -> dict[str, Any]:
    volume_gap = target_avg_volume - candidate_avg_volume if target_avg_volume is not None and candidate_avg_volume is not None else None
    amount_gap = target_avg_amount - candidate_avg_amount if target_avg_amount is not None and candidate_avg_amount is not None else None
    return {
        "target_vs_candidate_avg_weekly_volume_gap": _number(volume_gap),
        "target_vs_candidate_avg_weekly_volume_ratio": _number(_safe_ratio(target_avg_volume, candidate_avg_volume)),
        "target_vs_candidate_avg_weekly_amount_gap": _number(amount_gap),
        "target_vs_candidate_avg_weekly_amount_ratio": _number(_safe_ratio(target_avg_amount, candidate_avg_amount)),
    }


def _add_role(roles: dict[str, set[str]], code: str | None, role: str) -> None:
    if not code:
        return
    normalized = str(code).strip()
    if not normalized:
        return
    roles.setdefault(normalized, set()).add(role)


def _add_role_list(roles: dict[str, set[str]], codes: Sequence[Any] | None, role: str) -> None:
    for code in codes or []:
        _add_role(roles, str(code), role)


def _code_overlap(
    target_roles: dict[str, set[str]],
    candidate_roles: dict[str, set[str]],
    *,
    primary_key: str | None,
) -> dict[str, Any]:
    del primary_key
    target_codes = set(target_roles)
    candidate_codes = set(candidate_roles)
    matched = target_codes & candidate_codes
    union = target_codes | candidate_codes
    score = Decimal(len(matched)) / Decimal(len(union)) if union else Decimal("0")
    target_items = [
        {"code": code, "roles": sorted(target_roles.get(code, set()))}
        for code in sorted(target_codes)
    ]
    candidate_items = [
        {"code": code, "roles": sorted(candidate_roles.get(code, set()))}
        for code in sorted(candidate_codes)
    ]
    weighted = weighted_overlap_from_roles({"target_items": target_items, "candidate_items": candidate_items})
    return {
        "target_codes": sorted(target_codes),
        "candidate_codes": sorted(candidate_codes),
        "matched_codes": sorted(matched),
        "target_only_codes": sorted(target_codes - candidate_codes),
        "candidate_only_codes": sorted(candidate_codes - target_codes),
        "target_items": target_items,
        "candidate_items": candidate_items,
        "matched_items": [
            {
                "code": code,
                "target_roles": sorted(target_roles.get(code, set())),
                "candidate_roles": sorted(candidate_roles.get(code, set())),
            }
            for code in sorted(matched)
        ],
        "target_count": len(target_codes),
        "candidate_count": len(candidate_codes),
        "matched_count": len(matched),
        "union_count": len(union),
        "overlap_score": _number(score),
        **weighted,
    }


def _user_task_code_roles(row: entities.Core3M09cSkuUserTaskProfile | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    if row is None:
        return roles
    _add_role(roles, row.primary_user_task_code, "primary")
    _add_role_list(roles, row.secondary_user_task_codes_json, "secondary")
    _add_role_list(roles, row.comment_observed_task_codes_json, "comment_observed")
    _add_role_list(roles, row.brand_claimed_task_codes_json, "brand_claimed")
    _add_role_list(roles, row.latent_capability_task_codes_json, "latent_capability")
    _add_role_list(roles, row.drag_factor_task_codes_json, "drag_factor")
    return roles


def _target_group_code_roles(row: entities.Core3M10cSkuTargetGroupProfile | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    if row is None:
        return roles
    _add_role(roles, row.primary_target_group_code, "primary")
    _add_role_list(roles, row.secondary_target_group_codes_json, "secondary")
    _add_role_list(roles, row.comment_observed_group_codes_json, "comment_observed")
    _add_role_list(roles, row.brand_claimed_group_codes_json, "brand_claimed")
    _add_role_list(roles, row.latent_group_codes_json, "latent")
    _add_role_list(roles, row.unmet_group_need_codes_json, "unmet_need")
    return roles


def _battlefield_code_roles(row: entities.Core3SkuValueBattlefieldProfile | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    if row is None:
        return roles
    _add_role(roles, row.primary_battlefield_code, "primary")
    _add_role_list(roles, row.secondary_battlefield_codes_json, "secondary")
    _add_role_list(roles, row.opportunity_battlefield_codes_json, "opportunity")
    _add_role_list(roles, row.drag_factor_battlefield_codes_json, "drag_factor")
    return roles


def _param_code_roles(row: entities.Core3SkuParamProfile | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    if row is None:
        return roles
    for code in (row.param_values_json or {}):
        if code != "dimension_tier_profile":
            _add_role(roles, code, "param_value")
    for role, values in (
        ("picture", row.core_picture_params_json),
        ("gaming", row.core_gaming_params_json),
        ("system", row.core_system_params_json),
        ("eye_care", row.core_eye_care_params_json),
    ):
        for code in (values or {}):
            _add_role(roles, code, f"core_{role}")
    return roles


def _claim_code_roles(row: entities.Core3SkuClaimFactProfile | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    if row is None:
        return roles
    _add_role_list(roles, row.fact_claim_codes, "fact_claim")
    _add_role_list(roles, row.claim_codes, "claim")
    _add_role_list(roles, row.unsupported_claim_codes, "unsupported")
    return roles


def _claim_position_roles(row: entities.Core3SkuClaimFactProfile | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    if row is None:
        return roles
    for code, source_path in _flatten_position_codes(row.dimension_position_profile_json or {}):
        _add_role(roles, code, source_path)
    return roles


def _flatten_position_codes(value: Any, *, path: str = "dimension_position") -> list[tuple[str, str]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [(value, path)] if value.strip() else []
    if isinstance(value, list):
        result: list[tuple[str, str]] = []
        for item in value:
            result.extend(_flatten_position_codes(item, path=path))
        return result
    if isinstance(value, dict):
        result = []
        for key, item in value.items():
            result.extend(_flatten_position_codes(item, path=f"{path}:{key}"))
        return result
    return []


def _comment_param_support(row: entities.Core3SkuCommentFactProfile, param_code: str) -> dict[str, Any]:
    details = (row.param_comment_support_json or {}).get(param_code) or {}
    return {
        "source_type": "param_code",
        "code": param_code,
        "support_status": _support_status(
            code=param_code,
            positive_codes=row.supported_param_codes,
            negative_codes=row.contradicted_param_codes,
        ),
        "details": details,
    }


def _comment_claim_support(row: entities.Core3SkuCommentFactProfile, claim_code: str) -> dict[str, Any]:
    details = (row.claim_comment_support_json or {}).get(claim_code) or {}
    return {
        "source_type": "claim_code",
        "code": claim_code,
        "support_status": _support_status(
            code=claim_code,
            positive_codes=row.supported_claim_codes,
            negative_codes=row.contradicted_claim_codes,
        ),
        "details": details,
    }


def _comment_profile_code_support(source_type: str, code: str, roles: dict[str, set[str]]) -> dict[str, Any]:
    role_set = roles.get(code, set())
    if not role_set:
        support_status = "not_observed"
    elif role_set & {"comment_observed", "primary", "secondary"}:
        support_status = "supported_or_established"
    elif role_set & {"drag_factor", "unmet_need"}:
        support_status = "negative_or_unmet_need"
    elif role_set & {"brand_claimed", "latent", "latent_capability", "opportunity"}:
        support_status = "claimed_or_latent"
    else:
        support_status = "mentioned"
    return {
        "source_type": source_type,
        "code": code,
        "support_status": support_status,
        "roles": sorted(role_set),
    }


def _support_status(*, code: str, positive_codes: Sequence[Any] | None, negative_codes: Sequence[Any] | None) -> str:
    if code in {str(item) for item in positive_codes or []}:
        return "supported"
    if code in {str(item) for item in negative_codes or []}:
        return "contradicted"
    return "unmentioned"


def _opportunity_dimension_codes(
    battlefield: entities.Core3SkuValueBattlefieldProfile | None,
    allocations: Sequence[entities.Core3SemanticMarketAllocation],
) -> list[str]:
    if battlefield is None:
        return _unique_codes([row.dimension_code for row in allocations])
    return _unique_codes(
        [battlefield.primary_battlefield_code],
        battlefield.secondary_battlefield_codes_json,
        battlefield.opportunity_battlefield_codes_json,
        battlefield.drag_factor_battlefield_codes_json,
        [row.dimension_code for row in allocations],
    )


def _unique_codes(*groups: Sequence[Any] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        for value in group or []:
            if value is None:
                continue
            code = str(value).strip()
            if not code or code in seen:
                continue
            seen.add(code)
            result.append(code)
    return result


def _opportunity_market_position(
    row: entities.Core3SkuMarketProfile | None,
    param: entities.Core3SkuParamProfile | None,
) -> dict[str, Any]:
    param_tiers = (param.param_values_json or {}).get("dimension_tier_profile") if param else {}
    fact_size_tier = (param_tiers or {}).get("size")
    if row is None:
        return {"size_tier": fact_size_tier} if fact_size_tier else {}
    market_size_tier = row.size_segment
    payload: dict[str, Any] = {
        "screen_size_inch": _number(row.screen_size_inch),
        "size_tier": fact_size_tier or market_size_tier,
        "market_size_tier": market_size_tier,
        "price_band_in_size_tier": row.price_band_size,
        "price_wavg": _number(row.price_wavg),
        "price_percentile_in_size": _number(row.price_percentile_in_size),
        "volume_percentile_in_size": _number(row.volume_percentile_in_size),
        "avg_weekly_sales_volume": _number(_safe_avg(_decimal(row.sales_volume_total), row.active_week_count)),
        "same_pool_sku_count": row.same_pool_sku_count,
        "confidence_level": row.confidence_level,
    }
    if fact_size_tier and market_size_tier and fact_size_tier != market_size_tier:
        payload["size_tier_note_cn"] = "size_tier 优先采用 M03B 参数事实画像五档口径，market_size_tier 保留 M07 原市场池字段。"
    return payload


def _dimension_gap_items(
    codes: Sequence[str],
    *,
    summary_by_code: dict[str, entities.Core3SemanticMarketDimensionSummary],
    allocation_by_code: dict[str, entities.Core3SemanticMarketAllocation],
    default_relation_status: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in codes:
        summary = summary_by_code.get(code)
        allocation = allocation_by_code.get(code)
        items.append(
            {
                "dimension_code": code,
                "dimension_name": (summary.dimension_name if summary else None) or (allocation.dimension_name if allocation else None),
                "relation_status": allocation.relation_status if allocation else default_relation_status,
                "allocation_role": allocation.allocation_role if allocation else None,
                "market_space": _semantic_summary_payload(summary) if summary else {},
                "sku_allocation": _allocation_payload(allocation) if allocation else {},
            }
        )
    return items


def _price_gap_signals(row: entities.Core3SkuMarketProfile | None) -> list[dict[str, Any]]:
    if row is None:
        return [_gap_signal("price", "market_profile_missing", "unknown", "缺少 M07 市场画像，无法判断价格带和尺寸池位置。")]
    signals: list[dict[str, Any]] = []
    price_pct = _decimal(row.price_percentile_in_size)
    volume_pct = _decimal(row.volume_percentile_in_size)
    if price_pct is not None and volume_pct is not None:
        if price_pct >= Decimal("0.800000") and volume_pct <= Decimal("0.500000"):
            signals.append(
                _gap_signal(
                    "price",
                    "high_price_weak_volume",
                    "risk",
                    "同尺寸价格分位高但销量分位不高，可能存在价格或价值感压力。",
                    price_percentile_in_size=_number(price_pct),
                    volume_percentile_in_size=_number(volume_pct),
                )
            )
        if price_pct <= Decimal("0.300000") and volume_pct >= Decimal("0.700000"):
            signals.append(
                _gap_signal(
                    "price",
                    "low_price_strong_volume",
                    "advantage",
                    "同尺寸价格分位低且销量分位高，当前价格可能是销量支撑因素。",
                    price_percentile_in_size=_number(price_pct),
                    volume_percentile_in_size=_number(volume_pct),
                )
            )
        if price_pct <= Decimal("0.400000") and volume_pct <= Decimal("0.400000"):
            signals.append(
                _gap_signal(
                    "price",
                    "low_price_weak_volume",
                    "risk",
                    "价格不高但销量分位也不高，问题可能不只在价格，需要看参数、卖点或评论支撑。",
                    price_percentile_in_size=_number(price_pct),
                    volume_percentile_in_size=_number(volume_pct),
                )
            )
    if not signals:
        signals.append(_gap_signal("price", "no_clear_price_gap", "neutral", "价格分位和销量分位没有形成明显价格缺口信号。"))
    return signals


def _param_gap_signals(
    param: entities.Core3SkuParamProfile | None,
    comment: entities.Core3SkuCommentFactProfile | None,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if param is None:
        return [_gap_signal("parameter", "param_profile_missing", "unknown", "缺少 M03B 参数事实画像，无法判断参数能力缺口。")]
    if param.unknown_param_count:
        signals.append(
            _gap_signal(
                "parameter",
                "unknown_param_count",
                "risk",
                "部分参数仍未知，后续判断机会战场时需要避免把未知当作无能力。",
                unknown_param_count=param.unknown_param_count,
            )
        )
    if param.conflict_count:
        signals.append(
            _gap_signal(
                "parameter",
                "param_conflict_count",
                "review_required",
                "存在参数冲突，进入机会判断前应优先复核。",
                conflict_count=param.conflict_count,
            )
        )
    if param.review_required_count:
        signals.append(
            _gap_signal(
                "parameter",
                "param_review_required",
                "review_required",
                "部分参数需要人工复核，影响机会战场判断置信度。",
                review_required_count=param.review_required_count,
            )
        )
    for code in (comment.contradicted_param_codes if comment else []):
        signals.append(
            _gap_signal(
                "parameter",
                "comment_param_contradiction",
                "risk",
                "评论中存在对该参数或能力的负向反馈。",
                param_code=code,
                support_detail=(comment.param_comment_support_json or {}).get(code) if comment else None,
            )
        )
    if not signals:
        signals.append(_gap_signal("parameter", "no_clear_param_gap", "neutral", "当前参数画像未发现明确缺口信号。"))
    return signals


def _claim_gap_signals(
    claim: entities.Core3SkuClaimFactProfile | None,
    comment: entities.Core3SkuCommentFactProfile | None,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if claim is None:
        return [_gap_signal("claim", "claim_profile_missing", "unknown", "缺少 M04C 卖点事实画像，无法判断卖点缺口。")]
    if claim.unsupported_claim_codes:
        signals.append(
            _gap_signal(
                "claim",
                "unsupported_claim_codes",
                "risk",
                "存在缺少参数事实支撑的卖点，不能直接作为溢价卖点。",
                claim_codes=claim.unsupported_claim_codes,
            )
        )
    if claim.fact_claim_count == 0:
        signals.append(_gap_signal("claim", "no_fact_claim", "risk", "没有形成事实卖点，机会分析缺少可验证卖点锚点。"))
    for code in (comment.contradicted_claim_codes if comment else []):
        signals.append(
            _gap_signal(
                "claim",
                "comment_claim_contradiction",
                "risk",
                "评论中存在对该卖点的负向反馈。",
                claim_code=code,
                support_detail=(comment.claim_comment_support_json or {}).get(code) if comment else None,
            )
        )
    if not signals:
        signals.append(_gap_signal("claim", "no_clear_claim_gap", "neutral", "当前卖点画像未发现明确缺口信号。"))
    return signals


def _comment_gap_signals(row: entities.Core3SkuCommentFactProfile | None) -> list[dict[str, Any]]:
    if row is None:
        return [_gap_signal("comment", "comment_profile_missing", "unknown", "缺少 M05C 评论事实画像，无法判断用户侧机会和风险。")]
    signals: list[dict[str, Any]] = []
    if row.negative_sentence_count:
        signals.append(
            _gap_signal(
                "comment",
                "negative_comment_signal",
                "risk",
                "评论事实中存在负向产品体验，机会判断需要区分需求强但产品未满足的情况。",
                negative_sentence_count=row.negative_sentence_count,
            )
        )
    if row.product_fact_sentence_count == 0:
        signals.append(_gap_signal("comment", "no_product_fact_comment", "unknown", "评论中没有产品事实句，用户侧支撑不足。"))
    confidence = _decimal(row.confidence)
    if confidence is not None and confidence < Decimal("0.6000"):
        signals.append(
            _gap_signal(
                "comment",
                "low_comment_confidence",
                "review_required",
                "评论事实画像置信度偏低，后续结论需要复核。",
                confidence=_number(confidence),
            )
        )
    if not signals:
        signals.append(_gap_signal("comment", "no_clear_comment_gap", "neutral", "当前评论事实未发现明显负向缺口信号。"))
    return signals


def _semantic_gap_signals(
    task: entities.Core3M09cSkuUserTaskProfile | None,
    group: entities.Core3M10cSkuTargetGroupProfile | None,
    battlefield: entities.Core3SkuValueBattlefieldProfile | None,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if task is None:
        signals.append(_gap_signal("semantic", "user_task_profile_missing", "unknown", "缺少用户任务画像。"))
    else:
        if not task.primary_user_task_code:
            signals.append(
                _gap_signal(
                    "semantic",
                    "no_primary_user_task",
                    "risk",
                    "没有主用户任务，机会判断需要先确认真实用户目的。",
                    no_primary_reason=task.no_primary_reason,
                )
            )
        if task.drag_factor_task_codes_json:
            signals.append(
                _gap_signal(
                    "semantic",
                    "drag_factor_user_tasks",
                    "risk",
                    "存在拖后腿用户任务，说明用户有需求但产品支撑不足。",
                    user_task_codes=task.drag_factor_task_codes_json,
                )
            )
    if group is None:
        signals.append(_gap_signal("semantic", "target_group_profile_missing", "unknown", "缺少目标客群画像。"))
    else:
        if not group.primary_target_group_code:
            signals.append(_gap_signal("semantic", "no_primary_target_group", "risk", "没有主目标客群，机会判断缺少明确人群锚点。"))
        if group.unmet_group_need_codes_json:
            signals.append(
                _gap_signal(
                    "semantic",
                    "unmet_target_group_needs",
                    "risk",
                    "存在未满足客群需求，可能是机会也可能是短板。",
                    target_group_codes=group.unmet_group_need_codes_json,
                )
            )
    if battlefield is None:
        signals.append(_gap_signal("semantic", "battlefield_profile_missing", "unknown", "缺少价值战场画像。"))
    else:
        if not battlefield.primary_battlefield_code:
            signals.append(_gap_signal("semantic", "no_primary_battlefield", "risk", "没有主价值战场，竞品和机会分析需要先确定竞争池。"))
        if battlefield.opportunity_battlefield_codes_json:
            signals.append(
                _gap_signal(
                    "semantic",
                    "opportunity_battlefields_present",
                    "opportunity",
                    "存在可进一步分析的机会战场。",
                    battlefield_codes=battlefield.opportunity_battlefield_codes_json,
                )
            )
        if battlefield.drag_factor_battlefield_codes_json:
            signals.append(
                _gap_signal(
                    "semantic",
                    "drag_factor_battlefields_present",
                    "risk",
                    "存在拖后腿战场，相关卖点不能直接判为溢价。",
                    battlefield_codes=battlefield.drag_factor_battlefield_codes_json,
                )
            )
    if not signals:
        signals.append(_gap_signal("semantic", "no_clear_semantic_gap", "neutral", "语义画像未发现明显机会或短板信号。"))
    return signals


def _gap_signal(signal_type: str, code: str, severity: str, message_cn: str, **details: Any) -> dict[str, Any]:
    return {
        "signal_type": signal_type,
        "gap_code": code,
        "severity": severity,
        "message_cn": message_cn,
        "details": {key: value for key, value in details.items() if value not in (None, [], {})},
    }
