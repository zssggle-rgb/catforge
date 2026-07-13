"""Repository helpers for CatForge analyst commands."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from itertools import groupby
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import ResolvedSku
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    ComparablePoolTierFact,
    EvidenceRef,
    LineageGate,
    LineageIssue,
    MarketCellRow,
    PurchaseReasonSnapshot,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
    SkuIdentity,
    SourceAuthority,
    SourceStatus,
)
from app.services.core3_real_data.analyst.competitor_answer import weighted_overlap_from_roles
from app.services.core3_real_data.analyst.purchase_reason_profile_reader import (
    PurchaseReasonProfileLookupKey,
    PurchaseReasonProfileReader,
    RepositoryPurchaseReasonProfileReader,
)
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_AC_RULE_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_AC_RULE_VERSION,
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M11D_RULE_VERSION,
    CORE3_M12C_RULE_VERSION,
    CORE3_M12C_AC_RULE_VERSION,
    CORE3_M12C_TV_RULE_VERSION,
    CORE3_M14_RULE_VERSION,
)
from app.services.core3_real_data.purchase_reason_context_builder import (
    SkuPurchaseReasonContextBuilder,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


SKU_CODE_RE = re.compile(r"\b(?:TV|AC)\d{6,}\b", re.IGNORECASE)
SERVING_SCOPE_BATCH_ID_PREFIX = "serving-scope:"
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
M12C_ROLE_UNIQUE = "unique_payment_potential"

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
    M12C_ROLE_UNIQUE: 3,
    M12C_ROLE_BASIC: 4,
    M12C_ROLE_HIGH_PRICE_INTERCEPT: 5,
    M12C_ROLE_PRICE_UP: 6,
    M12C_ROLE_WEAK_USER: 7,
    M12C_ROLE_USER_NEED: 8,
    M12C_ROLE_DRAG: 9,
    M12C_ROLE_OPPORTUNITY: 10,
    M12C_ROLE_BRAND: 11,
    M12C_ROLE_SAMPLE: 12,
}

M12C_BUSINESS_CLAIM_TYPE_PRIORITY = {
    "高溢价卖点": 0,
    "份额转化卖点": 1,
    "客户获得价值卖点": 2,
    "人无我有型支付价值卖点": 3,
    "待激活卖点": 4,
    "门槛卖点": 5,
    "厂家主张卖点": 6,
    "竞品拦截卖点": 7,
    "价格压力卖点": 8,
    "样本不足待复核": 9,
}


class AnalystRepository:
    def __init__(self, db: Session, *, project_id: str, category_code: str) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = category_code

    def latest_batch_id(self, *, product_category: str | None = None) -> str | None:
        if product_category:
            serving_batch_ids = self.latest_serving_scope_batch_ids(product_category=product_category)
            if len(serving_batch_ids) > 1:
                return format_serving_scope_batch_id(product_category, serving_batch_ids)
            if len(serving_batch_ids) == 1:
                return serving_batch_ids[0]
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

    def list_authoritative_sku_codes(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str,
    ) -> list[str]:
        """Return the complete current M07 SKU scope for one product category."""

        normalized_category = product_category.upper()
        stmt = (
            select(entities.Core3SkuMarketProfile.sku_code)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SkuMarketProfile.batch_id, batch_id))
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .where(
                entities.Core3SkuMarketProfile.sku_code.like(
                    f"{self._sku_prefix(normalized_category)}%"
                )
            )
            .distinct()
            .order_by(entities.Core3SkuMarketProfile.sku_code)
        )
        return [str(sku_code) for sku_code in self.db.execute(stmt).scalars()]

    def latest_serving_scope_batch_ids(self, *, product_category: str) -> tuple[str, ...]:
        normalized_category = product_category.upper()
        sku_prefix = self._sku_prefix(normalized_category)
        batch_ids: set[str] = set()
        batch_ids.update(
            self._current_profile_batch_ids(
                entities.Core3SkuMarketProfile,
                rule_version=CORE3_M07_RULE_VERSION,
                sku_prefix=sku_prefix,
            )
        )
        batch_ids.update(self._current_m14_batch_ids(sku_prefix=sku_prefix))
        batch_ids.update(
            self._current_profile_batch_ids(
                entities.Core3SkuParamProfile,
                rule_version=CORE3_M03B_AC_RULE_VERSION if normalized_category == "AC" else CORE3_M03B_RULE_VERSION,
                sku_prefix=sku_prefix,
                requires_is_current=False,
            )
        )
        for model, rule_version in (
            (entities.Core3SkuClaimFactProfile, _claim_rule_version(normalized_category)),
            (entities.Core3SkuCommentFactProfile, _comment_rule_version(normalized_category)),
            (entities.Core3M09cSkuUserTaskProfile, _user_task_rule_version(normalized_category)),
            (entities.Core3M10cSkuTargetGroupProfile, _target_group_rule_version(normalized_category)),
            (entities.Core3SkuValueBattlefieldProfile, _battlefield_rule_version(normalized_category)),
        ):
            batch_ids.update(
                self._current_profile_batch_ids(
                    model,
                    rule_version=rule_version,
                    sku_prefix=sku_prefix,
                    product_category=normalized_category,
                )
            )
        batch_ids.update(
            self._current_dimension_batch_ids(
                entities.Core3SemanticMarketDimensionSummary,
                rule_version=CORE3_M11D_RULE_VERSION,
                product_category=normalized_category,
            )
        )
        if not batch_ids:
            return ()
        return self._order_batch_ids_newest_first(batch_ids)

    def _current_m14_batch_ids(self, *, sku_prefix: str) -> tuple[str, ...]:
        stmt = (
            select(entities.Core3CompetitorSelectionRun.batch_id)
            .where(entities.Core3CompetitorSelectionRun.project_id == self.project_id)
            .where(entities.Core3CompetitorSelectionRun.category_code == self.category_code)
            .where(entities.Core3CompetitorSelectionRun.target_sku_code.like(f"{sku_prefix}%"))
            .where(entities.Core3CompetitorSelectionRun.rule_version == CORE3_M14_RULE_VERSION)
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
            .where(entities.Core3CompetitorSelectionRun.processing_status.in_(("success", "warning")))
            .where(entities.Core3CompetitorSelectionRun.selection_status.in_(("success", "limited")))
            .where(entities.Core3CompetitorSelectionRun.selected_count > 0)
            .where(entities.Core3CompetitorSelectionRun.review_required.is_(False))
            .group_by(entities.Core3CompetitorSelectionRun.batch_id)
        )
        return tuple(str(batch_id) for batch_id in self.db.execute(stmt).scalars())

    def _current_profile_batch_ids(
        self,
        model: type[Any],
        *,
        rule_version: str,
        sku_prefix: str,
        product_category: str | None = None,
        requires_is_current: bool = True,
    ) -> tuple[str, ...]:
        stmt = (
            select(model.batch_id)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code)
            .where(model.rule_version == rule_version)
            .where(model.sku_code.like(f"{sku_prefix}%"))
            .group_by(model.batch_id)
        )
        if product_category is not None and hasattr(model, "product_category"):
            stmt = stmt.where(model.product_category == product_category)
        if requires_is_current and hasattr(model, "is_current"):
            stmt = stmt.where(model.is_current.is_(True))
        return tuple(str(batch_id) for batch_id in self.db.execute(stmt).scalars())

    def _current_dimension_batch_ids(
        self,
        model: type[Any],
        *,
        rule_version: str,
        product_category: str,
    ) -> tuple[str, ...]:
        stmt = (
            select(model.batch_id)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code)
            .where(model.product_category == product_category)
            .where(model.rule_version == rule_version)
            .where(model.is_current.is_(True))
            .group_by(model.batch_id)
        )
        return tuple(str(batch_id) for batch_id in self.db.execute(stmt).scalars())

    def _order_batch_ids_newest_first(self, batch_ids: Iterable[str]) -> tuple[str, ...]:
        batch_id_tuple = tuple(dict.fromkeys(batch_ids))
        stmt = (
            select(entities.Core3SourceBatch.batch_id)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code)
            .where(entities.Core3SourceBatch.batch_id.in_(batch_id_tuple))
            .order_by(desc(entities.Core3SourceBatch.scan_started_at), desc(entities.Core3SourceBatch.batch_id))
        )
        ordered = [str(batch_id) for batch_id in self.db.execute(stmt).scalars()]
        ordered_set = set(ordered)
        ordered.extend(sorted(batch_id for batch_id in batch_id_tuple if batch_id not in ordered_set))
        return tuple(ordered)

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
            .where(_batch_filter(entities.Core3SkuMarketProfile.batch_id, batch_id))
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
        )
        if sku_code:
            stmt = base_stmt.where(entities.Core3SkuMarketProfile.sku_code == sku_code.upper())
            rows = list(
                self.db.execute(
                    stmt.order_by(
                        _batch_order_expr(entities.Core3SkuMarketProfile.batch_id, batch_id),
                        entities.Core3SkuMarketProfile.sku_code,
                    ).limit(limit)
                ).scalars()
            )
        elif model_name:
            sku_prefix_filter = entities.Core3SkuMarketProfile.sku_code.like(f"{self._sku_prefix(product_category)}%")
            rows = []
            for model_variant in _model_query_variants(model_name):
                exact_stmt = (
                    base_stmt.where(entities.Core3SkuMarketProfile.model_name.ilike(model_variant))
                    .where(sku_prefix_filter)
                    .order_by(
                        _batch_order_expr(entities.Core3SkuMarketProfile.batch_id, batch_id),
                        entities.Core3SkuMarketProfile.sku_code,
                    )
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
                        .order_by(
                            _batch_order_expr(entities.Core3SkuMarketProfile.batch_id, batch_id),
                            entities.Core3SkuMarketProfile.sku_code,
                        )
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
            .where(_batch_filter(entities.Core3SkuParamProfile.batch_id, batch_id))
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
        )
        if sku_code:
            stmt = base_stmt.where(entities.Core3SkuParamProfile.sku_code == sku_code.upper())
            rows = list(
                self.db.execute(
                    stmt.order_by(
                        _batch_order_expr(entities.Core3SkuParamProfile.batch_id, batch_id),
                        entities.Core3SkuParamProfile.sku_code,
                    ).limit(limit)
                ).scalars()
            )
        elif model_name:
            sku_prefix_filter = entities.Core3SkuParamProfile.sku_code.like(f"{self._sku_prefix(product_category)}%")
            rows = []
            for model_variant in _model_query_variants(model_name):
                exact_stmt = (
                    base_stmt.where(entities.Core3SkuParamProfile.model_name.ilike(model_variant))
                    .where(sku_prefix_filter)
                    .order_by(
                        _batch_order_expr(entities.Core3SkuParamProfile.batch_id, batch_id),
                        entities.Core3SkuParamProfile.sku_code,
                    )
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
                        .order_by(
                            _batch_order_expr(entities.Core3SkuParamProfile.batch_id, batch_id),
                            entities.Core3SkuParamProfile.sku_code,
                        )
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
        if market_payload and battlefield_profile is not None:
            market_position = market_payload.setdefault("market_position", {})
            battlefield_price_band = battlefield_profile.price_band_in_size_tier
            if battlefield_profile.size_tier and not market_position.get("size_tier"):
                market_position["size_tier"] = battlefield_profile.size_tier
                market_position["size_tier_source"] = "M11C"
            if battlefield_price_band and battlefield_price_band != "unknown" and not _known_value(market_position.get("price_band_in_size_tier")):
                market_position["price_band_in_size_tier"] = battlefield_price_band
                market_position["price_band_source"] = "M11C"
                market_position["price_percentile_in_size"] = _number(battlefield_profile.price_percentile_in_size_tier)
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

    def sellpoint_value_evidence_context(
        self,
        *,
        batch_id: str,
        sku: ResolvedSku,
        product_category: str,
        market_window: str,
        analysis_population: str,
        fallback_candidates: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Load published evidence for the product-manager sellpoint analysis.

        M14 is the only native competitor selector used here. Callers may pass
        candidate identifiers produced by the existing competitor SOP when M14
        has no current selection; final competitor narratives and M12C values
        are intentionally not consumed.
        """

        normalized_category = product_category.upper()
        target_fact = self.sku_fact_brief(
            batch_id=batch_id,
            sku=sku,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
        )
        target_source_rows = {
            "M03B": self._param_profile(batch_id=batch_id, product_category=normalized_category, sku_code=sku.sku_code),
            "M04C": self._claim_profile(batch_id=batch_id, product_category=normalized_category, sku_code=sku.sku_code),
            "M05C": self._comment_profile(batch_id=batch_id, product_category=normalized_category, sku_code=sku.sku_code),
            "M07": self._market_profile(batch_id=batch_id, sku_code=sku.sku_code, market_window=market_window),
            "M09C": self._user_task_profile(batch_id=batch_id, product_category=normalized_category, sku_code=sku.sku_code),
            "M10C": self._target_group_profile(batch_id=batch_id, product_category=normalized_category, sku_code=sku.sku_code),
            "M11C": self._battlefield_profile(batch_id=batch_id, product_category=normalized_category, sku_code=sku.sku_code),
        }
        selection_rows = self._sellpoint_competitor_selections(
            batch_id=batch_id,
            target_sku_code=sku.sku_code,
        )
        competitor_source = "M14" if selection_rows else "none"
        competitor_refs: list[dict[str, Any]] = [
            _sellpoint_competitor_selection_payload(row)
            for row in selection_rows
        ]
        if not competitor_refs and fallback_candidates:
            competitor_source = "competitor_set_fallback"
            seen: set[str] = set()
            for rank, item in enumerate(fallback_candidates, start=1):
                candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else item
                sku_code = str((candidate or {}).get("sku_code") or "").strip()
                if not sku_code or sku_code in seen or sku_code == sku.sku_code:
                    continue
                seen.add(sku_code)
                competitor_refs.append(
                    {
                        "sku_code": sku_code,
                        "brand_name": (candidate or {}).get("brand_name"),
                        "model_name": (candidate or {}).get("model_name"),
                        "selection_rank": rank,
                        "slot_code": item.get("competitor_role") or item.get("role") or "existing_competitor_sop",
                        "slot_name_cn": item.get("competitor_role_cn") or item.get("role_cn") or "既有竞品智能体候选",
                        "selection_confidence": _number(item.get("confidence")) or _number(item.get("business_score")),
                        "evidence_completeness_score": _number(item.get("evidence_completeness_score")),
                        "selection_source": "competitor_set_fallback",
                        "selection_evidence_ids": [],
                    }
                )
                if len(competitor_refs) >= 3:
                    break
        sku_codes = [sku.sku_code, *[str(item["sku_code"]) for item in competitor_refs]]
        atoms = self._sellpoint_comment_atoms(
            batch_id=batch_id,
            product_category=normalized_category,
            sku_codes=sku_codes,
        )
        weekly_rows = self._sellpoint_market_weekly_rows(
            batch_id=batch_id,
            sku_codes=sku_codes,
            market_window=market_window,
        )
        atoms_by_sku: dict[str, list[dict[str, Any]]] = {}
        for row in atoms:
            atoms_by_sku.setdefault(row.sku_code, []).append(_sellpoint_comment_atom_payload(row))
        weekly_by_sku: dict[str, list[dict[str, Any]]] = {}
        for row in weekly_rows:
            if row.sku_code:
                weekly_by_sku.setdefault(row.sku_code, []).append(_sellpoint_market_weekly_payload(row))
        competitors: list[dict[str, Any]] = []
        for reference in competitor_refs:
            competitor_sku = self._resolved_sku_for_sellpoint(
                batch_id=batch_id,
                product_category=normalized_category,
                market_window=market_window,
                sku_code=str(reference["sku_code"]),
                fallback=reference,
            )
            if competitor_sku is None:
                continue
            competitors.append(
                {
                    **reference,
                    "fact_brief": self.sku_fact_brief(
                        batch_id=batch_id,
                        sku=competitor_sku,
                        product_category=normalized_category,
                        market_window=market_window,
                        analysis_population=analysis_population,
                    ),
                    "comment_atoms": atoms_by_sku.get(competitor_sku.sku_code, []),
                    "market_weekly_rows": weekly_by_sku.get(competitor_sku.sku_code, []),
                }
            )
        evidence_ids = _dedupe_texts(
            [
                *(item for row in atoms for item in (row.evidence_ids or [])),
                *(row.clean_market_id for row in weekly_rows),
                *(item for row in selection_rows for item in (row.evidence_ids or [])),
            ]
        )
        return {
            "schema_version": "sellpoint_value_pm_context_v1",
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": batch_id,
            "product_category": normalized_category,
            "market_window": market_window,
            "target": sku.to_dict(),
            "fact_brief": target_fact,
            "comment_atoms": atoms_by_sku.get(sku.sku_code, []),
            "market_weekly_rows": weekly_by_sku.get(sku.sku_code, []),
            "competitor_source": competitor_source,
            "competitor_selection_batch_id": selection_rows[0].batch_id if selection_rows else None,
            "competitors": competitors,
            "purchase_reason_hypothesis": {},
            "source_versions": {
                **{
                    module: str(getattr(row, "rule_version"))
                    for module, row in target_source_rows.items()
                    if row is not None and getattr(row, "rule_version", None)
                },
                **({"M14": str(selection_rows[0].rule_version)} if selection_rows else {}),
            },
            "evidence_ids": evidence_ids,
        }

    def sellpoint_value_v4_context(
        self,
        *,
        batch_id: str,
        sku: ResolvedSku,
        product_category: str,
        market_window: str,
        analysis_population: str,
        fallback_candidates: Sequence[dict[str, Any]] | None = None,
        m12d_profile_version: str | None = None,
        purchase_reason_reader: PurchaseReasonProfileReader | None = None,
    ) -> SellpointValueV4Context:
        """Build the immutable read-only V4 evidence context.

        This method deliberately returns facts and lineage only. It does not
        infer user value, assign counterfactual roles, or calculate WTP.
        """

        normalized_category = product_category.upper()
        if normalized_category not in {"TV", "AC"}:
            raise ValueError("sellpoint value V4 supports TV and AC only")
        serving_batch_ids = tuple(batch_ids_from_scope(batch_id)) or (batch_id,)

        selection_rows = self._sellpoint_competitor_selections(
            batch_id=batch_id,
            target_sku_code=sku.sku_code,
        )
        candidate_refs = _v4_candidate_references(
            target_sku_code=sku.sku_code,
            selection_rows=selection_rows,
            fallback_candidates=fallback_candidates,
        )
        sku_codes = _dedupe_texts([sku.sku_code, *(item["sku_code"] for item in candidate_refs)])

        profile_specs: dict[str, dict[str, Any]] = {
            "M03B": {
                "model": entities.Core3SkuParamProfile,
                "table_name": "core3_sku_param_profile",
                "rule_version": CORE3_M03B_AC_RULE_VERSION if normalized_category == "AC" else CORE3_M03B_RULE_VERSION,
                "record_id_attr": "sku_param_profile_id",
                "result_hash_attr": "profile_hash",
                "requires_current": False,
            },
            "M04C": {
                "model": entities.Core3SkuClaimFactProfile,
                "table_name": "core3_sku_claim_fact_profile",
                "rule_version": _claim_rule_version(normalized_category),
                "taxonomy_version": CORE3_M04C_AC_TAXONOMY_VERSION if normalized_category == "AC" else CORE3_M04C_TV_TAXONOMY_VERSION,
                "record_id_attr": "claim_profile_id",
                "result_hash_attr": "profile_hash",
            },
            "M05C": {
                "model": entities.Core3SkuCommentFactProfile,
                "table_name": "core3_sku_comment_fact_profile",
                "rule_version": _comment_rule_version(normalized_category),
                "taxonomy_version": CORE3_M05C_AC_TAXONOMY_VERSION if normalized_category == "AC" else CORE3_M05C_TV_TAXONOMY_VERSION,
                "record_id_attr": "comment_profile_id",
                "result_hash_attr": "profile_hash",
            },
            "M07": {
                "model": entities.Core3SkuMarketProfile,
                "table_name": "core3_sku_market_profile",
                "rule_version": CORE3_M07_RULE_VERSION,
                "record_id_attr": "profile_id",
                "result_hash_attr": "result_hash",
                "extra_filters": {"analysis_window": market_window},
            },
            "M09C": {
                "model": entities.Core3M09cSkuUserTaskProfile,
                "table_name": "core3_m09c_sku_user_task_profile",
                "rule_version": _user_task_rule_version(normalized_category),
                "taxonomy_version": CORE3_M09C_AC_TAXONOMY_VERSION if normalized_category == "AC" else CORE3_M09C_TV_TAXONOMY_VERSION,
                "record_id_attr": "profile_id",
                "result_hash_attr": "profile_hash",
            },
            "M10C": {
                "model": entities.Core3M10cSkuTargetGroupProfile,
                "table_name": "core3_m10c_sku_target_group_profile",
                "rule_version": _target_group_rule_version(normalized_category),
                "taxonomy_version": CORE3_M10C_AC_TAXONOMY_VERSION if normalized_category == "AC" else CORE3_M10C_TV_TAXONOMY_VERSION,
                "record_id_attr": "profile_id",
                "result_hash_attr": "profile_hash",
            },
            "M11C": {
                "model": entities.Core3SkuValueBattlefieldProfile,
                "table_name": "core3_sku_value_battlefield_profile",
                "rule_version": _battlefield_rule_version(normalized_category),
                "taxonomy_version": CORE3_M11C_AC_TAXONOMY_VERSION if normalized_category == "AC" else CORE3_M11C_TV_TAXONOMY_VERSION,
                "record_id_attr": "profile_id",
                "result_hash_attr": "profile_hash",
            },
        }
        selected_by_module: dict[str, dict[str, Any]] = {}
        ambiguous_by_module: dict[str, set[str]] = {}
        current_authorities: list[SourceAuthority] = []
        for module_code, spec in profile_specs.items():
            rows = self._v4_configured_profile_rows(
                batch_id=batch_id,
                sku_codes=sku_codes,
                product_category=normalized_category,
                **spec,
            )
            selected, ambiguous = _v4_pick_rows_by_key(
                rows,
                requested_batch_id=batch_id,
                key_fn=lambda row: str(row.sku_code),
            )
            selected_by_module[module_code] = selected
            ambiguous_by_module[module_code] = ambiguous
            refs = [
                _v4_row_evidence_ref(
                    module_code,
                    row,
                    record_type=spec["table_name"],
                    record_id_attr=spec["record_id_attr"],
                    result_hash_attr=spec["result_hash_attr"],
                )
                for row in selected.values()
            ]
            current_authorities.append(
                _v4_configured_authority(
                    module_code=module_code,
                    table_name=spec["table_name"],
                    rule_version=spec["rule_version"],
                    taxonomy_version=spec.get("taxonomy_version"),
                    sku_codes=sku_codes,
                    selected=selected,
                    ambiguous=ambiguous,
                    refs=refs,
                )
            )

        allocation_rows, summary_rows, m11d_ambiguous = self._v4_semantic_market_rows(
            batch_id=batch_id,
            sku_codes=sku_codes,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
        )
        allocation_by_sku: dict[str, list[Any]] = defaultdict(list)
        for row in allocation_rows:
            allocation_by_sku[str(row.sku_code)].append(row)
        m11d_refs = [
            *[
                _v4_row_evidence_ref(
                    "M11D",
                    row,
                    record_type="core3_semantic_market_allocation",
                    record_id_attr="allocation_id",
                    result_hash_attr="result_hash",
                )
                for row in allocation_rows
            ],
            *[
                _v4_row_evidence_ref(
                    "M11D",
                    row,
                    record_type="core3_semantic_market_dimension_summary",
                    record_id_attr="summary_id",
                    result_hash_attr="result_hash",
                )
                for row in summary_rows
            ],
        ]
        current_authorities.append(
            _v4_multirow_authority(
                module_code="M11D",
                table_name="core3_semantic_market_allocation+core3_semantic_market_dimension_summary",
                rule_version=CORE3_M11D_RULE_VERSION,
                rows=[*allocation_rows, *summary_rows],
                refs=m11d_refs,
                ambiguous_keys=m11d_ambiguous,
            )
        )

        m12c_pool_tiers, m12c_rows_by_sku, m12c_refs, m12c_ambiguous = self._v4_m12c_pool_tiers(
            batch_id=batch_id,
            sku_codes=sku_codes,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
        )
        current_authorities.append(
            _v4_multirow_authority(
                module_code="M12C",
                table_name="core3_sku_claim_value_quantification+core3_claim_value_context_pool",
                rule_version=_m12c_rule_version(normalized_category),
                rows=m12c_refs,
                refs=m12c_refs,
                ambiguous_keys=m12c_ambiguous,
            )
        )

        comment_atoms = self._v4_comment_atoms(
            selected_profiles=selected_by_module["M05C"],
            product_category=normalized_category,
        )
        atoms_by_sku: dict[str, list[Any]] = defaultdict(list)
        for row in comment_atoms:
            atoms_by_sku[str(row.sku_code)].append(row)

        weekly_rows = self._v4_market_weekly_rows(
            selected_profiles=selected_by_module["M07"]
        )
        weekly_rows, market_cells_truncated = _v4_trim_market_weekly_rows(
            weekly_rows,
            limit=2000,
        )
        if market_cells_truncated:
            current_authorities = [
                authority.model_copy(
                    update={
                        "usability": "limited",
                        "warnings": _dedupe_texts(
                            [*authority.warnings, "market_cells_truncated"]
                        ),
                    }
                )
                if authority.module_code == "M07"
                else authority
                for authority in current_authorities
            ]
        market_cells = _v4_market_cells(
            weekly_rows=weekly_rows,
            market_profiles=selected_by_module["M07"],
            battlefield_profiles=selected_by_module["M11C"],
            allocation_rows=allocation_rows,
        )

        reader = purchase_reason_reader or RepositoryPurchaseReasonProfileReader(self.db)
        purchase_contract = reader.read(
            PurchaseReasonProfileLookupKey(
                project_id=self.project_id,
                category_code=self.category_code,
                batch_id=batch_id,
                sku_code=sku.sku_code,
                m12d_profile_version=m12d_profile_version,
            )
        )
        published_lineage = _v4_published_lineage(purchase_contract)
        current_m12d_context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=self.db,
                project_id=self.project_id,
                category_code=self.category_code,
            )
        ).build_context(
            batch_id=batch_id,
            sku_code=sku.sku_code,
            product_category=normalized_category,
        )
        current_m12d_lineage = _v4_current_m12d_input_lineage(
            current_m12d_context,
            requested_batch_id=batch_id,
        )
        lineage_gate = build_sellpoint_value_v4_lineage_gate(
            published_lineage=published_lineage,
            current_validation_lineage=current_m12d_lineage,
        )
        purchase_snapshot, m12d_authority = _v4_purchase_reason_snapshot(
            purchase_contract,
            lineage_status=lineage_gate.status,
        )

        m14_authority = _v4_candidate_authority(
            selection_rows=selection_rows,
            candidate_refs=candidate_refs,
        )
        authority_manifest = [*current_authorities, m12d_authority, m14_authority]

        snapshots: dict[str, SkuEvidenceSnapshot] = {}
        for sku_code in sku_codes:
            snapshots[sku_code] = _v4_sku_snapshot(
                sku_code=sku_code,
                target_fallback=sku if sku_code == sku.sku_code else None,
                candidate_ref=next((item for item in candidate_refs if item["sku_code"] == sku_code), None),
                selected_by_module=selected_by_module,
                ambiguous_by_module=ambiguous_by_module,
                allocation_rows=allocation_by_sku.get(sku_code, []),
                summary_rows=summary_rows,
                m11d_ambiguous=m11d_ambiguous,
                m12c_present=bool(m12c_rows_by_sku.get(sku_code)),
                m12c_ambiguous=m12c_ambiguous,
                comment_atoms=atoms_by_sku.get(sku_code, []),
                product_category=normalized_category,
            )

        candidate_snapshots = [
            snapshots[item["sku_code"]]
            for item in candidate_refs
            if item["sku_code"] in snapshots
        ]
        all_refs = _v4_dedupe_evidence_refs(
            [
                *snapshots[sku.sku_code].source_refs,
                *(ref for snapshot in candidate_snapshots for ref in snapshot.source_refs),
                *m11d_refs,
                *m12c_refs,
                *(ref for item in candidate_refs for ref in (item.get("source_refs") or [])),
                *(cell.source_ref for cell in market_cells),
                *purchase_snapshot.source_refs,
            ]
        )
        target_identity = snapshots[sku.sku_code].identity
        context_payload = {
            "schema_version": "sellpoint_value_v4_context_v1",
            "project_id": self.project_id,
            "category_code": normalized_category,
            "requested_batch_id": batch_id,
            "serving_batch_ids": list(serving_batch_ids),
            "market_window": market_window,
            "target": target_identity,
            "authority_manifest": authority_manifest,
            "lineage_gate": lineage_gate,
            "target_snapshot": snapshots[sku.sku_code],
            "purchase_reason_profile": purchase_snapshot,
            "candidate_snapshots": candidate_snapshots,
            "market_cells": market_cells,
            "m12c_pool_tiers": m12c_pool_tiers,
            "evidence_refs": all_refs,
        }
        return SellpointValueV4Context(
            **context_payload,
            input_hash=canonical_v4_hash(context_payload),
        )

    def _v4_configured_profile_rows(
        self,
        *,
        model: type[Any],
        batch_id: str,
        sku_codes: Sequence[str],
        product_category: str,
        table_name: str,
        rule_version: str,
        record_id_attr: str,
        result_hash_attr: str,
        taxonomy_version: str | None = None,
        requires_current: bool = True,
        extra_filters: dict[str, Any] | None = None,
    ) -> list[Any]:
        del table_name, record_id_attr, result_hash_attr
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code)
            .where(_batch_filter(model.batch_id, batch_id))
            .where(model.sku_code.in_(tuple(sku_codes)))
            .where(model.rule_version == rule_version)
        )
        if hasattr(model, "product_category"):
            stmt = stmt.where(model.product_category == product_category)
        if taxonomy_version is not None and hasattr(model, "taxonomy_version"):
            stmt = stmt.where(model.taxonomy_version == taxonomy_version)
        if requires_current and hasattr(model, "is_current"):
            stmt = stmt.where(model.is_current.is_(True))
        for field_name, value in (extra_filters or {}).items():
            stmt = stmt.where(getattr(model, field_name) == value)
        return list(self.db.execute(stmt).scalars())

    def _v4_semantic_market_rows(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
        product_category: str,
        market_window: str,
        analysis_population: str,
    ) -> tuple[list[Any], list[Any], set[str]]:
        allocation_stmt = (
            select(entities.Core3SemanticMarketAllocation)
            .where(entities.Core3SemanticMarketAllocation.project_id == self.project_id)
            .where(entities.Core3SemanticMarketAllocation.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SemanticMarketAllocation.batch_id, batch_id))
            .where(entities.Core3SemanticMarketAllocation.product_category == product_category)
            .where(entities.Core3SemanticMarketAllocation.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketAllocation.market_window == market_window)
            .where(entities.Core3SemanticMarketAllocation.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3SemanticMarketAllocation.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketAllocation.is_current.is_(True))
        )
        allocation_candidates = list(self.db.execute(allocation_stmt).scalars())
        selected_allocations, allocation_ambiguous = _v4_pick_rows_by_key(
            allocation_candidates,
            requested_batch_id=batch_id,
            key_fn=lambda row: (str(row.sku_code), str(row.dimension_type), str(row.dimension_code)),
        )
        allocation_rows = sorted(
            selected_allocations.values(),
            key=lambda row: (str(row.sku_code), str(row.dimension_type), -float(row.allocation_weight), str(row.dimension_code)),
        )

        dimension_keys = {(str(row.dimension_type), str(row.dimension_code)) for row in allocation_rows}
        if not dimension_keys:
            return allocation_rows, [], allocation_ambiguous
        summary_stmt = (
            select(entities.Core3SemanticMarketDimensionSummary)
            .where(entities.Core3SemanticMarketDimensionSummary.project_id == self.project_id)
            .where(entities.Core3SemanticMarketDimensionSummary.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SemanticMarketDimensionSummary.batch_id, batch_id))
            .where(entities.Core3SemanticMarketDimensionSummary.product_category == product_category)
            .where(entities.Core3SemanticMarketDimensionSummary.analysis_population == analysis_population)
            .where(entities.Core3SemanticMarketDimensionSummary.market_window == market_window)
            .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
        )
        summary_candidates = [
            row
            for row in self.db.execute(summary_stmt).scalars()
            if (str(row.dimension_type), str(row.dimension_code)) in dimension_keys
        ]
        selected_summaries, summary_ambiguous = _v4_pick_rows_by_key(
            summary_candidates,
            requested_batch_id=batch_id,
            key_fn=lambda row: (str(row.dimension_type), str(row.dimension_code)),
        )
        summary_rows = sorted(
            selected_summaries.values(),
            key=lambda row: (str(row.dimension_type), str(row.dimension_code)),
        )
        return allocation_rows, summary_rows, allocation_ambiguous | summary_ambiguous

    def _v4_m12c_pool_tiers(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
        product_category: str,
        market_window: str,
        analysis_population: str,
    ) -> tuple[list[ComparablePoolTierFact], dict[str, list[Any]], list[EvidenceRef], set[str]]:
        quant = entities.Core3SkuClaimValueQuantification
        m12c_population = _sellpoint_m12c_population(
            product_category, analysis_population
        )
        quant_stmt = (
            select(
                quant.sku_claim_value_id,
                quant.pool_id,
                quant.batch_id,
                quant.sku_code,
                quant.claim_code,
                quant.claim_name,
                quant.claim_dimension,
                quant.claim_value_role,
                quant.context_type,
                quant.context_code,
                quant.size_tier,
                quant.price_band_group,
                quant.supporting_dimensions_json,
                quant.evidence_ids_json,
                quant.result_hash,
                quant.rule_version,
            )
            .where(quant.project_id == self.project_id)
            .where(quant.category_code == self.category_code)
            .where(_batch_filter(quant.batch_id, batch_id))
            .where(quant.product_category == product_category)
            .where(quant.market_window == market_window)
            .where(quant.analysis_population == m12c_population)
            .where(quant.sku_code.in_(tuple(sku_codes)))
            .where(quant.rule_version == _m12c_rule_version(product_category))
            .where(quant.is_current.is_(True))
        )
        quant_candidates = list(self.db.execute(quant_stmt).all())
        selected_quant, quant_ambiguous = _v4_pick_rows_by_key(
            quant_candidates,
            requested_batch_id=batch_id,
            key_fn=lambda row: (
                str(row.sku_code),
                str(row.claim_code),
                str(row.context_type),
                str(row.context_code),
                str(row.size_tier),
                str(row.price_band_group),
            ),
        )
        quant_rows = list(selected_quant.values())
        pool_ids = _dedupe_texts(row.pool_id for row in quant_rows if row.pool_id)
        pools: list[Any] = []
        if pool_ids:
            pool = entities.Core3ClaimValueContextPool
            pool_stmt = (
                select(pool)
                .where(pool.project_id == self.project_id)
                .where(pool.category_code == self.category_code)
                .where(pool.pool_id.in_(tuple(pool_ids)))
                .where(pool.rule_version == _m12c_rule_version(product_category))
                .where(pool.is_current.is_(True))
            )
            pools = list(self.db.execute(pool_stmt).scalars())
        pools_by_id = {str(row.pool_id): row for row in pools}
        facts: list[ComparablePoolTierFact] = []
        for row in sorted(pools, key=lambda item: (str(item.claim_code), str(item.context_type), str(item.context_code))):
            quality_flags = [str(item) for item in (row.quality_flags_json or [])]
            comparison_basis = next(
                (item.removeprefix("comparison_basis:") for item in quality_flags if item.startswith("comparison_basis:")),
                "claim_presence",
            )
            comparison_param_code = next(
                (item.removeprefix("comparison_param:") for item in quality_flags if item.startswith("comparison_param:")),
                None,
            )
            facts.append(
                ComparablePoolTierFact(
                    claim_code=str(row.claim_code),
                    bundle_code=str(row.claim_code),
                    context_code=str(row.context_code),
                    comparison_basis=comparison_basis,
                    comparison_param_code=comparison_param_code,
                    pool_sku_count=int(row.pool_sku_count),
                    with_count=int(row.with_claim_sku_count),
                    without_count=int(row.without_claim_sku_count),
                    unknown_count=int(row.unknown_claim_sku_count),
                    sample_status=str(row.sample_status),
                    quality_flags=quality_flags,
                    pool_hash=str(row.pool_hash),
                )
            )
        refs = [
            *[
                EvidenceRef(
                    module_code="M12C",
                    record_type="core3_sku_claim_value_quantification",
                    record_id=str(row.sku_claim_value_id),
                    result_hash=str(row.result_hash),
                    batch_id=str(row.batch_id),
                    rule_version=str(row.rule_version),
                    evidence_ids=list(row.evidence_ids_json or []),
                )
                for row in quant_rows
            ],
            *[
                EvidenceRef(
                    module_code="M12C",
                    record_type="core3_claim_value_context_pool",
                    record_id=str(row.pool_id),
                    result_hash=str(row.pool_hash),
                    batch_id=str(row.batch_id),
                    rule_version=str(row.rule_version),
                    evidence_ids=[],
                )
                for row in pools
            ],
        ]
        rows_by_sku: dict[str, list[Any]] = defaultdict(list)
        for row in quant_rows:
            rows_by_sku[str(row.sku_code)].append(row)
        missing_pool_ids = {str(row.pool_id) for row in quant_rows if row.pool_id and str(row.pool_id) not in pools_by_id}
        ambiguous = quant_ambiguous | {f"missing_pool:{pool_id}" for pool_id in missing_pool_ids}
        return facts, rows_by_sku, _v4_dedupe_evidence_refs(refs), ambiguous

    def _v4_comment_atoms(
        self,
        *,
        selected_profiles: dict[str, Any],
        product_category: str,
    ) -> list[entities.Core3CommentFactAtom]:
        if not selected_profiles:
            return []
        profile_batches = {sku_code: str(row.batch_id) for sku_code, row in selected_profiles.items()}
        stmt = (
            select(entities.Core3CommentFactAtom)
            .where(entities.Core3CommentFactAtom.project_id == self.project_id)
            .where(entities.Core3CommentFactAtom.category_code == self.category_code)
            .where(entities.Core3CommentFactAtom.batch_id.in_(tuple(set(profile_batches.values()))))
            .where(entities.Core3CommentFactAtom.product_category == product_category)
            .where(entities.Core3CommentFactAtom.sku_code.in_(tuple(profile_batches)))
            .where(
                entities.Core3CommentFactAtom.taxonomy_version
                == (CORE3_M05C_AC_TAXONOMY_VERSION if product_category == "AC" else CORE3_M05C_TV_TAXONOMY_VERSION)
            )
            .where(entities.Core3CommentFactAtom.rule_version == _comment_rule_version(product_category))
            .where(entities.Core3CommentFactAtom.is_current.is_(True))
            .order_by(
                entities.Core3CommentFactAtom.sku_code,
                entities.Core3CommentFactAtom.source_comment_key,
                entities.Core3CommentFactAtom.sentence_seq,
                entities.Core3CommentFactAtom.subdimension_code,
            )
        )
        result: list[entities.Core3CommentFactAtom] = []
        seen: set[tuple[str, str, int | None, str]] = set()
        for row in self.db.execute(stmt).scalars():
            if str(row.batch_id) != profile_batches.get(str(row.sku_code)):
                continue
            key = (str(row.sku_code), str(row.source_comment_key), row.sentence_seq, str(row.subdimension_code))
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _v4_market_weekly_rows(
        self,
        *,
        selected_profiles: dict[str, Any],
    ) -> list[entities.Core3CleanMarketWeekly]:
        if not selected_profiles:
            return []
        profile_batches = {sku_code: str(row.batch_id) for sku_code, row in selected_profiles.items()}
        stmt = (
            select(entities.Core3CleanMarketWeekly)
            .where(entities.Core3CleanMarketWeekly.project_id == self.project_id)
            .where(entities.Core3CleanMarketWeekly.category_code == self.category_code)
            .where(entities.Core3CleanMarketWeekly.batch_id.in_(tuple(set(profile_batches.values()))))
            .where(entities.Core3CleanMarketWeekly.sku_code.in_(tuple(profile_batches)))
            .where(entities.Core3CleanMarketWeekly.period_week_index.is_not(None))
            .where(entities.Core3CleanMarketWeekly.record_status == "active")
            .where(entities.Core3CleanMarketWeekly.quality_status == "ok")
            .order_by(
                entities.Core3CleanMarketWeekly.period_week_index.desc(),
                entities.Core3CleanMarketWeekly.platform_type,
                entities.Core3CleanMarketWeekly.sku_code,
                entities.Core3CleanMarketWeekly.source_row_id,
            )
            .limit(2001)
        )
        result: list[entities.Core3CleanMarketWeekly] = []
        seen: set[str] = set()
        for row in self.db.execute(stmt).scalars():
            if str(row.batch_id) != profile_batches.get(str(row.sku_code)):
                continue
            key = str(row.clean_record_key)
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _sellpoint_competitor_selections(
        self,
        *,
        batch_id: str,
        target_sku_code: str,
    ) -> list[entities.Core3CompetitorSelection]:
        eligible_batch_ids = batch_ids_from_scope(batch_id)
        run_stmt = (
            select(entities.Core3CompetitorSelectionRun)
            .where(entities.Core3CompetitorSelectionRun.project_id == self.project_id)
            .where(entities.Core3CompetitorSelectionRun.category_code == self.category_code)
            .where(entities.Core3CompetitorSelectionRun.target_sku_code == target_sku_code)
            .where(entities.Core3CompetitorSelectionRun.rule_version == CORE3_M14_RULE_VERSION)
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
            .where(entities.Core3CompetitorSelectionRun.processing_status.in_(("success", "warning")))
            .where(entities.Core3CompetitorSelectionRun.selection_status.in_(("success", "limited")))
            .where(entities.Core3CompetitorSelectionRun.selected_count > 0)
            .where(entities.Core3CompetitorSelectionRun.review_required.is_(False))
            .order_by(
                entities.Core3CompetitorSelectionRun.updated_at.desc(),
                entities.Core3CompetitorSelectionRun.created_at.desc(),
                entities.Core3CompetitorSelectionRun.selection_run_id.desc(),
            )
            .limit(1)
        )
        if eligible_batch_ids:
            run_stmt = run_stmt.where(entities.Core3CompetitorSelectionRun.batch_id.in_(eligible_batch_ids))
        selection_run = self.db.execute(run_stmt).scalar_one_or_none()
        if selection_run is None:
            return []
        stmt = (
            select(entities.Core3CompetitorSelection)
            .where(entities.Core3CompetitorSelection.project_id == self.project_id)
            .where(entities.Core3CompetitorSelection.category_code == self.category_code)
            .where(entities.Core3CompetitorSelection.batch_id == selection_run.batch_id)
            .where(entities.Core3CompetitorSelection.selection_run_id == selection_run.selection_run_id)
            .where(entities.Core3CompetitorSelection.target_sku_code == target_sku_code)
            .where(entities.Core3CompetitorSelection.rule_version == CORE3_M14_RULE_VERSION)
            .where(entities.Core3CompetitorSelection.is_current.is_(True))
            .where(entities.Core3CompetitorSelection.processing_status.in_(("success", "warning")))
            .where(entities.Core3CompetitorSelection.review_required.is_(False))
            .order_by(
                entities.Core3CompetitorSelection.selection_rank,
                entities.Core3CompetitorSelection.slot_code,
            )
        )
        result: list[entities.Core3CompetitorSelection] = []
        seen: set[str] = set()
        for row in self.db.execute(stmt).scalars():
            if row.candidate_sku_code in seen:
                continue
            seen.add(row.candidate_sku_code)
            result.append(row)
            if len(result) >= 30:
                break
        return result

    def _sellpoint_comment_atoms(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_codes: Sequence[str],
    ) -> list[entities.Core3CommentFactAtom]:
        if not sku_codes:
            return []
        result: list[entities.Core3CommentFactAtom] = []
        for sku_code in _dedupe_texts(sku_codes):
            profile = self._comment_profile(
                batch_id=batch_id,
                product_category=product_category,
                sku_code=sku_code,
            )
            if profile is None or not profile.batch_id:
                continue
            stmt = (
                select(entities.Core3CommentFactAtom)
                .where(entities.Core3CommentFactAtom.project_id == self.project_id)
                .where(entities.Core3CommentFactAtom.category_code == self.category_code)
                .where(entities.Core3CommentFactAtom.batch_id == profile.batch_id)
                .where(entities.Core3CommentFactAtom.product_category == product_category)
                .where(entities.Core3CommentFactAtom.sku_code == sku_code)
                .where(entities.Core3CommentFactAtom.rule_version == _comment_rule_version(product_category))
                .where(entities.Core3CommentFactAtom.is_current.is_(True))
                .order_by(
                    entities.Core3CommentFactAtom.source_comment_key,
                    entities.Core3CommentFactAtom.sentence_seq,
                    entities.Core3CommentFactAtom.subdimension_code,
                )
            )
            seen: set[tuple[str, int | None, str]] = set()
            for row in self.db.execute(stmt).scalars():
                key = (row.source_comment_key, row.sentence_seq, row.subdimension_code)
                if key in seen:
                    continue
                seen.add(key)
                result.append(row)
        return result

    def _sellpoint_market_weekly_rows(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
        market_window: str,
    ) -> list[entities.Core3CleanMarketWeekly]:
        if not sku_codes:
            return []
        result: list[entities.Core3CleanMarketWeekly] = []
        for sku_code in _dedupe_texts(sku_codes):
            profile = self._market_profile(
                batch_id=batch_id,
                sku_code=sku_code,
                market_window=market_window,
            )
            if profile is None or not profile.batch_id:
                continue
            stmt = (
                select(entities.Core3CleanMarketWeekly)
                .where(entities.Core3CleanMarketWeekly.project_id == self.project_id)
                .where(entities.Core3CleanMarketWeekly.category_code == self.category_code)
                .where(entities.Core3CleanMarketWeekly.batch_id == profile.batch_id)
                .where(entities.Core3CleanMarketWeekly.sku_code == sku_code)
                .where(entities.Core3CleanMarketWeekly.period_week_index.is_not(None))
                .where(entities.Core3CleanMarketWeekly.record_status == "active")
                .where(entities.Core3CleanMarketWeekly.quality_status == "ok")
                .order_by(
                    entities.Core3CleanMarketWeekly.period_week_index,
                    entities.Core3CleanMarketWeekly.platform_type,
                    entities.Core3CleanMarketWeekly.source_row_id,
                )
            )
            seen: set[str] = set()
            for row in self.db.execute(stmt).scalars():
                if row.clean_record_key in seen:
                    continue
                seen.add(row.clean_record_key)
                result.append(row)
        return result

    def _resolved_sku_for_sellpoint(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str,
        sku_code: str,
        fallback: dict[str, Any],
    ) -> ResolvedSku | None:
        market = self._market_profile(batch_id=batch_id, sku_code=sku_code, market_window=market_window)
        param = self._param_profile(batch_id=batch_id, product_category=product_category, sku_code=sku_code)
        if market is None and param is None:
            return None
        return ResolvedSku(
            sku_code=sku_code,
            brand_name=(market.brand_name or market.brand) if market is not None else fallback.get("brand_name"),
            model_name=(market.model_name if market is not None else None) or (param.model_name if param is not None else None) or fallback.get("model_name"),
            product_category=product_category,
            size_tier=(market.size_segment if market is not None else None) or _param_size_tier(param),
            price_band_in_size_tier=market.price_band_size if market is not None else None,
            screen_size_inch=_decimal(market.screen_size_inch) if market is not None else None,
            weighted_price=_decimal(market.price_wavg) if market is not None else None,
            avg_weekly_sales_volume=_safe_avg(_decimal(market.sales_volume_total), market.active_week_count) if market is not None else None,
            source="M14/M07" if market is not None else "M14/M03B",
        )

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
            .where(_batch_filter(entities.Core3SemanticMarketDimensionSummary.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SkuMarketProfile.batch_id, batch_id))
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
        match_policy = "m07_same_size_price_band"
        fallback_context: dict[str, Any] = {}
        if not rows:
            rows, fallback_context = self._m11c_comparable_battlefield_market_candidates(
                batch_id=batch_id,
                target_market=target_market,
                target_sku_code=target_sku_code,
                product_category=product_category,
                market_window=market_window,
                limit=limit,
            )
            if rows:
                match_policy = "m11c_comparable_value_battlefield_pool"
        return {
            "target_market": _candidate_market_payload(target_market, target_market=target_market),
            "match_policy": match_policy,
            "fallback_context": fallback_context,
            "candidates": [_candidate_market_payload(row, target_market=target_market) for row in rows],
        }

    def _m11c_comparable_battlefield_market_candidates(
        self,
        *,
        batch_id: str,
        target_market: entities.Core3SkuMarketProfile,
        target_sku_code: str,
        product_category: str,
        market_window: str,
        limit: int,
    ) -> tuple[list[entities.Core3SkuMarketProfile], dict[str, Any]]:
        product_category = product_category.upper()
        battlefield = self._battlefield_profile(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=target_sku_code,
        )
        if battlefield is None or not battlefield.primary_battlefield_code:
            return [], {}
        target_score = self._battlefield_score(
            batch_id=batch_id,
            product_category=product_category,
            sku_code=target_sku_code,
            battlefield_code=battlefield.primary_battlefield_code,
        )
        comparable_context = _m11c_comparable_market_context(target_score)
        comparison_size_tiers = [
            item
            for item in (comparable_context.get("comparison_size_tiers") or [])
            if isinstance(item, str) and item
        ]
        sample_peer_codes = _unique_codes(
            [
                item.get("peer_sku_code")
                for item in (comparable_context.get("sample_peer_comparisons") or [])
                if isinstance(item, dict)
            ]
        )
        battlefield_peer_codes = self._m11c_battlefield_peer_sku_codes(
            batch_id=batch_id,
            product_category=product_category,
            battlefield_code=battlefield.primary_battlefield_code,
            comparison_size_tiers=tuple(comparison_size_tiers),
            target_sku_code=target_sku_code,
            limit=limit,
        )
        candidate_codes = _unique_codes(sample_peer_codes, battlefield_peer_codes)
        if not candidate_codes:
            return [], {}
        rows_by_sku = self._market_profiles_by_sku(
            batch_id=batch_id,
            sku_codes=candidate_codes,
            product_category=product_category,
            market_window=market_window,
        )
        rows = [rows_by_sku[sku_code] for sku_code in candidate_codes if sku_code in rows_by_sku]
        sample_order = {sku_code: index for index, sku_code in enumerate(sample_peer_codes)}
        rows = sorted(
            rows,
            key=lambda row: (
                sample_order.get(row.sku_code, len(sample_order) + 1),
                _candidate_pool_sort_key(row, target_market),
            ),
        )
        if limit != 0:
            rows = rows[: max(limit, 0)]
        return rows, {
            "source_module": "M11C",
            "primary_battlefield_code": battlefield.primary_battlefield_code,
            "primary_relation_status": battlefield.primary_relation_status,
            "target_size_tier": battlefield.size_tier,
            "target_price_band_in_size_tier": battlefield.price_band_in_size_tier,
            "comparison_size_tiers": comparison_size_tiers,
            "borrowed_adjacent_context_pool": bool(comparable_context.get("borrowed_adjacent_context_pool")),
            "qualified_peer_count": comparable_context.get("qualified_peer_count"),
            "sample_peer_count": len(sample_peer_codes),
            "market_candidate_count": len(rows),
            "policy_note_cn": comparable_context.get("note_cn")
            or "M07 同尺寸池不足时，使用 M11C 主价值战场和已批准相邻分档可比池补充候选。",
        }

    def _battlefield_score(
        self,
        *,
        batch_id: str,
        product_category: str,
        sku_code: str,
        battlefield_code: str,
    ) -> entities.Core3SkuValueBattlefieldScore | None:
        stmt = (
            select(entities.Core3SkuValueBattlefieldScore)
            .where(entities.Core3SkuValueBattlefieldScore.project_id == self.project_id)
            .where(entities.Core3SkuValueBattlefieldScore.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SkuValueBattlefieldScore.batch_id, batch_id))
            .where(entities.Core3SkuValueBattlefieldScore.product_category == product_category.upper())
            .where(entities.Core3SkuValueBattlefieldScore.sku_code == sku_code)
            .where(entities.Core3SkuValueBattlefieldScore.battlefield_code == battlefield_code)
            .where(entities.Core3SkuValueBattlefieldScore.rule_version == _battlefield_rule_version(product_category))
            .where(entities.Core3SkuValueBattlefieldScore.is_current.is_(True))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _m11c_battlefield_peer_sku_codes(
        self,
        *,
        batch_id: str,
        product_category: str,
        battlefield_code: str,
        comparison_size_tiers: tuple[str, ...],
        target_sku_code: str,
        limit: int,
    ) -> list[str]:
        stmt = (
            select(entities.Core3SkuValueBattlefieldProfile)
            .where(entities.Core3SkuValueBattlefieldProfile.project_id == self.project_id)
            .where(entities.Core3SkuValueBattlefieldProfile.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SkuValueBattlefieldProfile.batch_id, batch_id))
            .where(entities.Core3SkuValueBattlefieldProfile.product_category == product_category.upper())
            .where(entities.Core3SkuValueBattlefieldProfile.sku_code != target_sku_code)
            .where(entities.Core3SkuValueBattlefieldProfile.primary_battlefield_code == battlefield_code)
            .where(entities.Core3SkuValueBattlefieldProfile.rule_version == _battlefield_rule_version(product_category))
            .where(entities.Core3SkuValueBattlefieldProfile.is_current.is_(True))
            .order_by(
                entities.Core3SkuValueBattlefieldProfile.confidence.desc(),
                entities.Core3SkuValueBattlefieldProfile.sku_code,
            )
        )
        if comparison_size_tiers:
            stmt = stmt.where(entities.Core3SkuValueBattlefieldProfile.size_tier.in_(comparison_size_tiers))
        if limit != 0:
            stmt = stmt.limit(max(limit * 5, limit, 50))
        return [row.sku_code for row in self.db.execute(stmt).scalars()]

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
            .where(_batch_filter(entities.Core3ClaimValueDimensionSummary.batch_id, batch_id))
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
        quant_rows_all = self._m12c_sku_claim_rows(
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
            limit=0,
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
        metric_by_id = self._m12c_metrics_by_id(row.metric_id for row in quant_rows_all)
        claim_value_payloads_all = [_sku_claim_value_payload(row, metric_by_id.get(row.metric_id or "")) for row in quant_rows_all]
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
            "role_counts": _count_by([row.claim_value_role for row in quant_rows_all]),
            "sku_level_claim_values": _sku_level_claim_value_summary(claim_value_payloads_all),
            "claim_values": claim_value_payloads_all[: max(limit, 0)] if limit else claim_value_payloads_all,
            "attributions": [_claim_attribution_payload(row) for row in attr_rows],
            "method_note_cn": "卖点支付价值先在单个价值战场内判断，再按战场相关度汇总到 SKU 层；可比池卖点价格差异/销量差异是有卖点组与对照组的可观测差异，不代表单一卖点因果增量。",
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
            .where(_batch_filter(entities.Core3SkuClaimValueQuantification.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SkuClaimContributionAttribution.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3CleanMarketWeekly.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SemanticMarketDimensionSummary.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SemanticMarketSkuContribution.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SkuMarketProfile.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SkuMarketProfile.batch_id, batch_id))
            .where(entities.Core3SkuMarketProfile.sku_code == sku_code)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .order_by(_batch_order_expr(entities.Core3SkuMarketProfile.batch_id, batch_id))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _market_profiles_by_sku(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
        product_category: str,
        market_window: str,
    ) -> dict[str, entities.Core3SkuMarketProfile]:
        if not sku_codes:
            return {}
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SkuMarketProfile.batch_id, batch_id))
            .where(entities.Core3SkuMarketProfile.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3SkuMarketProfile.sku_code.like(f"{self._sku_prefix(product_category.upper())}%"))
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .order_by(
                _batch_order_expr(entities.Core3SkuMarketProfile.batch_id, batch_id),
                entities.Core3SkuMarketProfile.sku_code,
            )
        )
        rows_by_sku: dict[str, entities.Core3SkuMarketProfile] = {}
        for row in self.db.execute(stmt).scalars():
            rows_by_sku.setdefault(row.sku_code, row)
        return rows_by_sku

    def _param_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuParamProfile | None:
        rule_version = CORE3_M03B_AC_RULE_VERSION if product_category == "AC" else CORE3_M03B_RULE_VERSION
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SkuParamProfile.batch_id, batch_id))
            .where(entities.Core3SkuParamProfile.sku_code == sku_code)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .order_by(_batch_order_expr(entities.Core3SkuParamProfile.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SkuParamProfile.batch_id, batch_id))
            .where(entities.Core3SkuParamProfile.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .order_by(
                _batch_order_expr(entities.Core3SkuParamProfile.batch_id, batch_id),
                entities.Core3SkuParamProfile.sku_code,
            )
        )
        rows_by_sku: dict[str, entities.Core3SkuParamProfile] = {}
        for row in self.db.execute(stmt).scalars():
            rows_by_sku.setdefault(row.sku_code, row)
        return rows_by_sku

    def _claim_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuClaimFactProfile | None:
        stmt = self._current_sku_profile_stmt(
            entities.Core3SkuClaimFactProfile,
            batch_id=batch_id,
            product_category=product_category.upper(),
            sku_code=sku_code,
            rule_version=_claim_rule_version(product_category),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _comment_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuCommentFactProfile | None:
        stmt = self._current_sku_profile_stmt(
            entities.Core3SkuCommentFactProfile,
            batch_id=batch_id,
            product_category=product_category.upper(),
            sku_code=sku_code,
            rule_version=_comment_rule_version(product_category),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _user_task_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3M09cSkuUserTaskProfile | None:
        stmt = self._current_sku_profile_stmt(
            entities.Core3M09cSkuUserTaskProfile,
            batch_id=batch_id,
            product_category=product_category.upper(),
            sku_code=sku_code,
            rule_version=_user_task_rule_version(product_category),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _target_group_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3M10cSkuTargetGroupProfile | None:
        stmt = self._current_sku_profile_stmt(
            entities.Core3M10cSkuTargetGroupProfile,
            batch_id=batch_id,
            product_category=product_category.upper(),
            sku_code=sku_code,
            rule_version=_target_group_rule_version(product_category),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _battlefield_profile(self, *, batch_id: str, product_category: str, sku_code: str) -> entities.Core3SkuValueBattlefieldProfile | None:
        stmt = self._current_sku_profile_stmt(
            entities.Core3SkuValueBattlefieldProfile,
            batch_id=batch_id,
            product_category=product_category.upper(),
            sku_code=sku_code,
            rule_version=_battlefield_rule_version(product_category),
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
        stmt = (
            select(entities.Core3SemanticMarketAllocation)
            .where(entities.Core3SemanticMarketAllocation.project_id == self.project_id)
            .where(entities.Core3SemanticMarketAllocation.category_code == self.category_code)
            .where(_batch_filter(entities.Core3SemanticMarketAllocation.batch_id, batch_id))
            .where(entities.Core3SemanticMarketAllocation.product_category == product_category.upper())
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
                .where(_batch_filter(entities.Core3SemanticMarketAllocation.batch_id, batch_id))
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
            .where(_batch_filter(entities.Core3SemanticMarketSkuContribution.batch_id, batch_id))
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
            .where(_batch_filter(model.batch_id, batch_id))
            .where(model.product_category == product_category)
            .where(model.sku_code == sku_code)
            .where(model.rule_version == rule_version)
            .where(model.is_current.is_(True))
            .order_by(_batch_order_expr(model.batch_id, batch_id))
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


def canonical_v4_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 for V4 context inputs."""

    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_v4_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_sellpoint_value_v4_lineage_gate(
    *,
    published_lineage: Sequence[SourceAuthority],
    current_validation_lineage: Sequence[SourceAuthority],
) -> LineageGate:
    """Compare published M12D inputs with the configured current facts.

    A changed version and changed hash is a conflict until a later goal adds a
    substantive revalidation rule. Missing versions are unresolved, never
    silently treated as aligned.
    """

    current_by_module = {item.module_code: item for item in current_validation_lineage}
    published_by_module = {item.module_code: item for item in published_lineage}
    if not published_by_module:
        issue = LineageIssue(
            code="published_lineage_missing",
            severity="warning",
            scope="source",
            message_cn="没有可用的已发布采购理由画像线谱，不能执行来源对齐校验。",
            affected_module_codes=[],
        )
        return LineageGate(
            status="unresolved",
            published_lineage=list(published_lineage),
            current_validation_lineage=list(current_validation_lineage),
            issues=[issue],
            blocked_reason_codes=[],
        )
    semantic_modules = (
        ("M09C_M10C_M11C",)
        if "M09C_M10C_M11C" in published_by_module
        or "M09C_M10C_M11C" in current_by_module
        else ("M09C", "M10C", "M11C")
    )
    required_modules = (
        "M03B",
        "M04C",
        "M05C",
        "M07",
        *semantic_modules,
        "M11D",
        "M12C",
    )
    issues: list[LineageIssue] = []
    stale_revalidated = False
    conflict = False
    unresolved = False
    for module_code in required_modules:
        published = published_by_module.get(module_code)
        current = current_by_module.get(module_code)
        published_missing = published is None or published.availability == "missing"
        current_missing = current is None or current.availability == "missing"
        if published_missing and current_missing:
            continue
        if published_missing:
            unresolved = True
            issues.append(
                LineageIssue(
                    code="published_lineage_missing",
                    severity="warning",
                    scope="source",
                    message_cn=f"已发布采购理由画像没有保存 {module_code} 的可比版本线谱。",
                    affected_module_codes=[module_code],
                )
            )
            continue
        if current_missing:
            unresolved = True
            issues.append(
                LineageIssue(
                    code="current_validation_source_missing",
                    severity="warning",
                    scope="source",
                    message_cn=f"当前验证范围缺少 {module_code}，不能核对已发布画像。",
                    affected_module_codes=[module_code],
                )
            )
            continue
        published_batches = set(published.selected_batch_ids)
        current_batches = set(current.selected_batch_ids)
        batch_overlap = bool(published_batches & current_batches)
        if (
            published.source_hash
            and current.source_hash
            and published.source_hash == current.source_hash
            and batch_overlap
        ):
            if published.rule_version != current.rule_version:
                stale_revalidated = True
            continue
        if not published.rule_version or not current.rule_version:
            unresolved = True
            issues.append(
                LineageIssue(
                    code="lineage_rule_version_missing",
                    severity="warning",
                    scope="source",
                    message_cn=f"{module_code} 缺少可比 rule version，不能判断是否对齐。",
                    affected_module_codes=[module_code],
                )
            )
            continue
        if published.rule_version == current.rule_version and batch_overlap:
            if not published.source_hash or not current.source_hash:
                unresolved = True
                issues.append(
                    LineageIssue(
                        code="lineage_source_hash_missing",
                        severity="warning",
                        scope="source",
                        message_cn=f"{module_code} 缺少可比 source hash，不能确认已发布画像与当前事实一致。",
                        affected_module_codes=[module_code],
                    )
                )
                continue
            if published.source_hash == current.source_hash:
                continue
            conflict = True
            issues.append(
                LineageIssue(
                    code="version_lineage_conflict",
                    severity="blocking",
                    scope="relation",
                    message_cn=(
                        f"已发布画像与当前验证使用相同 {module_code} rule version 和批次，"
                        "但记录 hash 已变化；受影响的价值和价格归因必须暂停。"
                    ),
                    affected_module_codes=[module_code],
                )
            )
            continue
        if (
            published.rule_version != current.rule_version
            and published.source_hash
            and published.source_hash == current.source_hash
        ):
            stale_revalidated = True
            continue
        conflict = True
        issues.append(
            LineageIssue(
                code="version_lineage_conflict",
                severity="blocking",
                scope="relation",
                message_cn=(
                    f"已发布画像使用 {module_code} {published.rule_version}，当前验证使用 "
                    f"{current.rule_version}，且记录 hash 不一致；受影响的价值和价格归因必须暂停。"
                ),
                affected_module_codes=[module_code],
            )
        )
    if conflict:
        status = "stale_conflict"
    elif unresolved:
        status = "unresolved"
    elif stale_revalidated:
        status = "stale_revalidated"
    else:
        status = "aligned"
    blocked = sorted({issue.code for issue in issues if issue.severity == "blocking"})
    return LineageGate(
        status=status,
        published_lineage=list(published_lineage),
        current_validation_lineage=list(current_validation_lineage),
        issues=issues,
        blocked_reason_codes=blocked,
    )


def _v4_json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def _v4_pick_rows_by_key(
    rows: Sequence[Any],
    *,
    requested_batch_id: str,
    key_fn: Any,
) -> tuple[dict[Any, Any], set[str]]:
    scope = tuple(batch_ids_from_scope(requested_batch_id)) or (requested_batch_id,)
    batch_rank = {batch_id: rank for rank, batch_id in enumerate(scope)}
    grouped: dict[Any, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    selected: dict[Any, Any] = {}
    ambiguous: set[str] = set()
    for key, candidates in grouped.items():
        best_rank = min(batch_rank.get(str(row.batch_id), len(batch_rank)) for row in candidates)
        winners = [row for row in candidates if batch_rank.get(str(row.batch_id), len(batch_rank)) == best_rank]
        if len(winners) != 1:
            ambiguous.add(json.dumps(key, ensure_ascii=False, sort_keys=True, default=str))
            continue
        selected[key] = winners[0]
    return selected, ambiguous


def _v4_candidate_references(
    *,
    target_sku_code: str,
    selection_rows: Sequence[entities.Core3CompetitorSelection],
    fallback_candidates: Sequence[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    m14_by_code = {
        str(row.candidate_sku_code): row
        for row in selection_rows
        if str(row.candidate_sku_code) != target_sku_code
    }
    if fallback_candidates is None:
        candidates = [
            {
                "sku_code": str(row.candidate_sku_code),
                "brand_name": row.candidate_brand_name,
                "model_name": row.candidate_model_name,
                "provenance": "M14",
                "selection_rank": int(row.selection_rank),
                "slot_code": row.slot_code,
                "selection_confidence": _number(row.confidence),
                "source_refs": [
                    _v4_row_evidence_ref(
                        "M14",
                        row,
                        record_type="core3_competitor_selection",
                        record_id_attr="competitor_selection_id",
                        result_hash_attr="result_hash",
                    )
                ],
            }
            for row in selection_rows
            if str(row.candidate_sku_code) != target_sku_code
        ]
        return _v4_select_snapshot_candidates(candidates, limit=0)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, item in enumerate(fallback_candidates or (), start=1):
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else item
        sku_code = str((candidate or {}).get("sku_code") or "").strip()
        if not sku_code or sku_code == target_sku_code or sku_code in seen:
            continue
        seen.add(sku_code)
        m14 = m14_by_code.get(sku_code)
        result.append(
            {
                "sku_code": sku_code,
                "brand_name": (candidate or {}).get("brand_name"),
                "model_name": (candidate or {}).get("model_name"),
                "provenance": item.get("candidate_source")
                or "competitor_set_fallback",
                "selection_rank": int(m14.selection_rank) if m14 else rank,
                "slot_code": (
                    m14.slot_code
                    if m14
                    else item.get("competitor_role")
                    or item.get("role")
                    or "existing_competitor_sop"
                ),
                "selection_confidence": (
                    _number(m14.confidence)
                    if m14
                    else _number(item.get("confidence"))
                    or _number(item.get("business_score"))
                ),
                "source_refs": (
                    [
                        _v4_row_evidence_ref(
                            "M14",
                            m14,
                            record_type="core3_competitor_selection",
                            record_id_attr="competitor_selection_id",
                            result_hash_attr="result_hash",
                        )
                    ]
                    if m14
                    else []
                ),
            }
        )
    return _v4_select_snapshot_candidates(result, limit=0)


def _v4_select_snapshot_candidates(
    candidates: Sequence[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Keep declared-role coverage; zero means the complete candidate set."""

    buckets: dict[str, list[dict[str, Any]]] = {
        "base_value": [],
        "same_value": [],
        "stretch_benchmark": [],
        "unknown": [],
    }
    for candidate in candidates:
        buckets[_v4_declared_candidate_bucket(candidate.get("slot_code"))].append(
            candidate
        )
    selected: list[dict[str, Any]] = []
    effective_limit = len(candidates) if limit == 0 else max(limit, 0)
    while len(selected) < effective_limit:
        added = False
        for bucket in (
            "base_value",
            "same_value",
            "stretch_benchmark",
            "unknown",
        ):
            if buckets[bucket] and len(selected) < effective_limit:
                selected.append(buckets[bucket].pop(0))
                added = True
        if not added:
            break
    return selected


def _v4_declared_candidate_bucket(slot_code: Any) -> str:
    slot = str(slot_code or "").strip().lower()
    if slot in {"base_value", "same_value", "stretch_benchmark"}:
        return slot
    if any(token in slot for token in ("base", "lower", "down")):
        return "base_value"
    if any(token in slot for token in ("stretch", "benchmark", "higher", "upper")):
        return "stretch_benchmark"
    if any(token in slot for token in ("same", "direct", "core")):
        return "same_value"
    return "unknown"


def _v4_row_evidence_ref(
    module_code: str,
    row: Any,
    *,
    record_type: str,
    record_id_attr: str,
    result_hash_attr: str,
) -> EvidenceRef:
    evidence_ids = getattr(row, "evidence_ids", None) or getattr(row, "evidence_ids_json", None) or []
    return EvidenceRef(
        module_code=module_code,
        record_type=record_type,
        record_id=str(getattr(row, record_id_attr)),
        result_hash=str(getattr(row, result_hash_attr)),
        batch_id=str(getattr(row, "batch_id")) if getattr(row, "batch_id", None) else None,
        rule_version=str(getattr(row, "rule_version")) if getattr(row, "rule_version", None) else None,
        evidence_ids=list(evidence_ids),
    )


def _v4_configured_authority(
    *,
    module_code: str,
    table_name: str,
    rule_version: str,
    taxonomy_version: str | None,
    sku_codes: Sequence[str],
    selected: dict[str, Any],
    ambiguous: set[str],
    refs: list[EvidenceRef],
) -> SourceAuthority:
    ordered_refs = _v4_sorted_evidence_refs(refs)
    missing = [sku_code for sku_code in sku_codes if sku_code not in selected and json.dumps(sku_code) not in ambiguous]
    warnings = [*(f"missing_sku:{sku_code}" for sku_code in missing), *(f"ambiguous_current:{key}" for key in sorted(ambiguous))]
    if refs:
        availability = "present"
        usability = "limited" if warnings else "usable"
    else:
        availability = "missing"
        usability = "unusable"
    return SourceAuthority(
        module_code=module_code,
        table_name=table_name,
        authority_mode="configured_rule",
        rule_version=rule_version,
        taxonomy_version=taxonomy_version,
        selected_batch_ids=sorted({ref.batch_id for ref in ordered_refs if ref.batch_id}),
        row_count=len(ordered_refs),
        availability=availability,
        usability=usability,
        source_hash=(
            canonical_v4_hash(
                [ref.model_dump(mode="json") for ref in ordered_refs]
            )
            if ordered_refs
            else None
        ),
        selected_reason="configured rule version, taxonomy when available, and serving-scope precedence",
        warnings=warnings,
    )


def _v4_multirow_authority(
    *,
    module_code: str,
    table_name: str,
    rule_version: str,
    rows: Sequence[Any],
    refs: list[EvidenceRef],
    ambiguous_keys: set[str],
) -> SourceAuthority:
    del rows
    ordered_refs = _v4_sorted_evidence_refs(refs)
    warnings = [f"ambiguous_current:{key}" for key in sorted(ambiguous_keys)]
    return SourceAuthority(
        module_code=module_code,
        table_name=table_name,
        authority_mode="configured_rule",
        rule_version=rule_version,
        selected_batch_ids=sorted({ref.batch_id for ref in ordered_refs if ref.batch_id}),
        row_count=len(ordered_refs),
        availability="present" if ordered_refs else "missing",
        usability=("limited" if warnings else "usable") if ordered_refs else "unusable",
        source_hash=(
            canonical_v4_hash(
                [ref.model_dump(mode="json") for ref in ordered_refs]
            )
            if ordered_refs
            else None
        ),
        selected_reason="configured rule version and serving-scope precedence; monetary M12C fields excluded",
        warnings=warnings,
    )


def _v4_sorted_evidence_refs(refs: Sequence[EvidenceRef]) -> list[EvidenceRef]:
    return sorted(
        refs,
        key=lambda ref: (
            ref.module_code,
            ref.record_type,
            ref.record_id,
            ref.result_hash,
            ref.batch_id or "",
        ),
    )


def _v4_candidate_authority(
    *,
    selection_rows: Sequence[entities.Core3CompetitorSelection],
    candidate_refs: Sequence[dict[str, Any]],
) -> SourceAuthority:
    if selection_rows:
        refs = _v4_dedupe_evidence_refs(
            [ref for item in candidate_refs for ref in (item.get("source_refs") or [])]
        )
        return SourceAuthority(
            module_code="M14",
            table_name="core3_competitor_selection",
            authority_mode="configured_rule",
            rule_version=CORE3_M14_RULE_VERSION,
            selected_batch_ids=sorted({ref.batch_id for ref in refs if ref.batch_id}),
            row_count=len(refs),
            availability="present",
            usability="usable",
            source_hash=canonical_v4_hash([ref.model_dump(mode="json") for ref in refs]),
            selected_reason="current successful reviewed M14 selection run",
        )
    if candidate_refs:
        payload = [
            {key: value for key, value in item.items() if key != "source_refs"}
            for item in candidate_refs
        ]
        return SourceAuthority(
            module_code="M14",
            table_name="existing_competitor_sop",
            authority_mode="fallback",
            rule_version=None,
            selected_batch_ids=[],
            row_count=len(candidate_refs),
            availability="present",
            usability="limited",
            source_hash=canonical_v4_hash(payload),
            selected_reason="M14 unavailable for target; caller supplied existing competitor analysis identifiers",
            warnings=["fallback_provenance_not_m14"],
        )
    return SourceAuthority(
        module_code="M14",
        table_name="core3_competitor_selection",
        authority_mode="configured_rule",
        rule_version=CORE3_M14_RULE_VERSION,
        selected_batch_ids=[],
        row_count=0,
        availability="missing",
        usability="unusable",
        source_hash=None,
        selected_reason="no current eligible M14 run and no explicit fallback candidates",
        warnings=["candidate_source_missing"],
    )


def _v4_external_ref(payload: dict[str, Any]) -> EvidenceRef:
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    result_hash = str(payload.get("result_hash") or "").strip() or canonical_v4_hash(payload)
    return EvidenceRef(
        module_code=str(payload.get("module_code") or "unknown"),
        record_type=str(payload.get("table_name") or "unknown"),
        record_id=str(payload.get("record_id") or canonical_v4_hash(payload)),
        result_hash=result_hash,
        batch_id=str(extra.get("batch_id")) if extra.get("batch_id") else None,
        rule_version=str(extra.get("rule_version")) if extra.get("rule_version") else None,
        evidence_ids=[str(item) for item in (payload.get("evidence_ids") or [])],
    )


def _v4_published_lineage(contract: Any) -> list[SourceAuthority]:
    if not contract.found or contract.profile is None:
        return []
    grouped: dict[str, list[tuple[dict[str, Any], EvidenceRef]]] = defaultdict(list)
    for raw in contract.profile.source_refs:
        if not isinstance(raw, dict) or not raw.get("module_code"):
            continue
        grouped[str(raw["module_code"])].append((raw, _v4_external_ref(raw)))
    result: list[SourceAuthority] = []
    for module_code, pairs in sorted(grouped.items()):
        refs = _v4_dedupe_evidence_refs([ref for _, ref in pairs])
        rule_versions = sorted(
            {
                str((raw.get("extra") or {}).get("rule_version"))
                for raw, _ in pairs
                if (raw.get("extra") or {}).get("rule_version")
            }
        )
        taxonomies = sorted(
            {
                str((raw.get("extra") or {}).get("taxonomy_version"))
                for raw, _ in pairs
                if (raw.get("extra") or {}).get("taxonomy_version")
            }
        )
        tables = sorted({ref.record_type for ref in refs})
        warnings = [] if len(rule_versions) <= 1 else ["multiple_published_rule_versions"]
        result.append(
            SourceAuthority(
                module_code=module_code,
                table_name="+".join(tables),
                authority_mode="published_release",
                rule_version=rule_versions[0] if len(rule_versions) == 1 else None,
                taxonomy_version=taxonomies[0] if len(taxonomies) == 1 else None,
                release_id=contract.profile.m12d_profile_version,
                selected_batch_ids=list(contract.profile.source_batch_ids),
                row_count=len(refs),
                availability="present",
                usability="limited" if warnings else "usable",
                source_hash=canonical_v4_hash([ref.model_dump(mode="json") for ref in refs]),
                selected_reason="source refs frozen inside the published M12D profile",
                warnings=warnings,
            )
        )
    return result


def _v4_current_m12d_input_lineage(
    context: Any,
    *,
    requested_batch_id: str,
) -> list[SourceAuthority]:
    """Rebuild the target-only lineage using M12D's own input contract.

    The analyst authority manifest covers the target and its comparison SKUs,
    while a published M12D profile freezes only the target SKU inputs.  Those
    two scopes must remain separate: this helper intentionally compares the
    published profile with a fresh, read-only M12D context for the same target.
    """

    grouped: dict[str, list[tuple[dict[str, Any], EvidenceRef]]] = defaultdict(list)
    for source_ref in context.source_refs_json:
        raw = source_ref.model_dump(mode="json")
        grouped[str(raw["module_code"])].append((raw, _v4_external_ref(raw)))

    expected_modules = (
        "M03B",
        "M04C",
        "M05C",
        "M07",
        "M09C_M10C_M11C",
        "M11D",
        "M12C",
    )
    selected_batch_ids = list(batch_ids_from_scope(requested_batch_id)) or [
        requested_batch_id
    ]
    result: list[SourceAuthority] = []
    for module_code in expected_modules:
        pairs = grouped.get(module_code, [])
        if not pairs:
            result.append(
                SourceAuthority(
                    module_code=module_code,
                    table_name="m12d_input_context",
                    authority_mode="configured_rule",
                    rule_version=None,
                    selected_batch_ids=[],
                    row_count=0,
                    availability="missing",
                    usability="unusable",
                    source_hash=None,
                    selected_reason="current target-only M12D input is missing",
                    warnings=["current_m12d_input_missing"],
                )
            )
            continue
        refs = _v4_dedupe_evidence_refs([ref for _, ref in pairs])
        rule_versions = sorted(
            {
                str((raw.get("extra") or {}).get("rule_version"))
                for raw, _ in pairs
                if (raw.get("extra") or {}).get("rule_version")
            }
        )
        taxonomies = sorted(
            {
                str((raw.get("extra") or {}).get("taxonomy_version"))
                for raw, _ in pairs
                if (raw.get("extra") or {}).get("taxonomy_version")
            }
        )
        tables = sorted({ref.record_type for ref in refs})
        warnings = [] if len(rule_versions) <= 1 else ["multiple_current_rule_versions"]
        result.append(
            SourceAuthority(
                module_code=module_code,
                table_name="+".join(tables),
                authority_mode="configured_rule",
                rule_version=rule_versions[0] if len(rule_versions) == 1 else None,
                taxonomy_version=taxonomies[0] if len(taxonomies) == 1 else None,
                selected_batch_ids=selected_batch_ids,
                row_count=len(refs),
                availability="present",
                usability="limited" if warnings else "usable",
                source_hash=canonical_v4_hash(
                    [ref.model_dump(mode="json") for ref in refs]
                ),
                selected_reason="fresh target-only M12D input context",
                warnings=warnings,
            )
        )
    return result


def _v4_purchase_reason_snapshot(
    contract: Any,
    *,
    lineage_status: str,
) -> tuple[PurchaseReasonSnapshot, SourceAuthority]:
    if not contract.found or contract.profile is None:
        return (
            PurchaseReasonSnapshot(
                found=False,
                lineage_status="unresolved",
                profile_version=None,
                release_id=None,
                anchors=[],
                review_required=False,
                source_refs=[],
            ),
            SourceAuthority(
                module_code="M12D",
                table_name="core3_sku_purchase_reason_profile",
                authority_mode="published_release",
                rule_version=None,
                selected_batch_ids=[],
                row_count=0,
                availability="missing",
                usability="unusable",
                source_hash=None,
                selected_reason="no published M12D profile found for the target in serving scope",
                warnings=["published_profile_missing"],
            ),
        )
    profile = contract.profile
    profile_payload = profile.model_dump(mode="json")
    profile_ref = EvidenceRef(
        module_code="M12D",
        record_type="core3_sku_purchase_reason_profile",
        record_id=f"{profile.sku_code}:{profile.m12d_profile_version}",
        result_hash=canonical_v4_hash(profile_payload),
        batch_id=profile.batch_id,
        rule_version=profile.rule_version,
        evidence_ids=[],
    )
    source_refs = _v4_dedupe_evidence_refs(
        [profile_ref, *[_v4_external_ref(raw) for raw in profile.source_refs if isinstance(raw, dict)]]
    )
    usability = {
        "published_ready": "usable",
        "published_degraded": "limited",
        "published_unusable": "unusable",
    }.get(str(contract.consumption_state), "unusable")
    return (
        PurchaseReasonSnapshot(
            found=True,
            lineage_status=lineage_status,
            profile_version=profile.m12d_profile_version,
            release_id=profile.m12d_profile_version,
            anchors=[anchor.model_dump(mode="json") for anchor in profile.anchors],
            review_required=bool(profile.review_required),
            source_refs=source_refs,
        ),
        SourceAuthority(
            module_code="M12D",
            table_name="core3_sku_purchase_reason_profile",
            authority_mode="published_release",
            rule_version=profile.rule_version,
            schema_version=profile.schema_version,
            release_id=profile.m12d_profile_version,
            selected_batch_ids=[profile.batch_id],
            row_count=1,
            availability="present",
            usability=usability,
            source_hash=profile_ref.result_hash,
            selected_reason="published M12D downstream read contract",
            warnings=list(profile.degradation_reasons),
        ),
    )


def _v4_sku_snapshot(
    *,
    sku_code: str,
    target_fallback: ResolvedSku | None,
    candidate_ref: dict[str, Any] | None,
    selected_by_module: dict[str, dict[str, Any]],
    ambiguous_by_module: dict[str, set[str]],
    allocation_rows: Sequence[Any],
    summary_rows: Sequence[Any],
    m11d_ambiguous: set[str],
    m12c_present: bool,
    m12c_ambiguous: set[str],
    comment_atoms: Sequence[entities.Core3CommentFactAtom],
    product_category: str,
) -> SkuEvidenceSnapshot:
    rows = {module: selected.get(sku_code) for module, selected in selected_by_module.items()}
    identity = _v4_sku_identity(
        sku_code=sku_code,
        market=rows.get("M07"),
        param=rows.get("M03B"),
        target_fallback=target_fallback,
        candidate_ref=candidate_ref,
        product_category=product_category,
    )
    source_status: dict[str, SourceStatus] = {}
    for module_code in ("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C"):
        ambiguous = json.dumps(sku_code) in ambiguous_by_module.get(module_code, set())
        if ambiguous:
            source_status[module_code] = SourceStatus(
                availability="present",
                usability="unusable",
                issue_codes=["multiple_current_same_rule"],
            )
        elif rows.get(module_code) is not None:
            source_status[module_code] = SourceStatus(availability="present", usability="usable")
        else:
            source_status[module_code] = SourceStatus(
                availability="missing",
                usability="unusable",
                issue_codes=["configured_source_missing"],
            )
    m11d_issues = ["multiple_current_same_rule"] if any(sku_code in key for key in m11d_ambiguous) else []
    source_status["M11D"] = SourceStatus(
        availability="present" if allocation_rows else "missing",
        usability="limited" if allocation_rows and m11d_issues else ("usable" if allocation_rows else "unusable"),
        issue_codes=m11d_issues or ([] if allocation_rows else ["configured_source_missing"]),
    )
    m12c_issues = ["multiple_current_same_rule"] if any(sku_code in key for key in m12c_ambiguous) else []
    source_status["M12C"] = SourceStatus(
        availability="present" if m12c_present else "missing",
        usability="limited" if m12c_present and m12c_issues else ("usable" if m12c_present else "unusable"),
        issue_codes=m12c_issues or ([] if m12c_present else ["configured_source_missing"]),
    )
    summary_by_dimension = {(str(row.dimension_type), str(row.dimension_code)): row for row in summary_rows}
    semantic_market = []
    for row in allocation_rows:
        summary = summary_by_dimension.get((str(row.dimension_type), str(row.dimension_code)))
        item = _allocation_payload(row)
        item["market_space"] = (
            {
                "estimated_sales_volume": _number(summary.estimated_sales_volume),
                "estimated_sales_amount": _number(summary.estimated_sales_amount),
                "allocated_sku_count": int(summary.allocated_sku_count),
                "allocation_coverage_rate": _number(summary.allocation_coverage_rate),
                "causal_purchase_attribution": False,
            }
            if summary is not None
            else None
        )
        semantic_market.append(item)
    facts = {
        "parameter_fact": _param_payload(rows.get("M03B")),
        "claim_fact": _claim_payload(rows.get("M04C")),
        "comment_fact": _comment_payload(rows.get("M05C")),
    }
    if candidate_ref is not None:
        facts["candidate_source"] = {
            "provenance": candidate_ref["provenance"],
            "selection_rank": candidate_ref.get("selection_rank"),
            "slot_code": candidate_ref.get("slot_code"),
            "selection_confidence": candidate_ref.get("selection_confidence"),
        }
    market = _market_payload(rows.get("M07"))
    tasks_payload = _user_task_payload(rows.get("M09C"))
    groups_payload = _target_group_payload(rows.get("M10C"))
    battlefields_payload = _battlefield_payload(rows.get("M11C"))
    refs = [
        *[
            _v4_profile_ref_for_module(module_code, row)
            for module_code, row in rows.items()
            if row is not None
        ],
        *[
            _v4_row_evidence_ref(
                "M11D",
                row,
                record_type="core3_semantic_market_allocation",
                record_id_attr="allocation_id",
                result_hash_attr="result_hash",
            )
            for row in allocation_rows
        ],
        *[
            _v4_row_evidence_ref(
                "M05C",
                row,
                record_type="core3_comment_fact_atom",
                record_id_attr="comment_fact_id",
                result_hash_attr="fact_hash",
            )
            for row in comment_atoms
        ],
        *(candidate_ref.get("source_refs") or [] if candidate_ref is not None else []),
    ]
    payload = {
        "identity": identity,
        "source_status": source_status,
        "facts": facts,
        "comment_outcomes": [_sellpoint_comment_atom_payload(row) for row in comment_atoms],
        "market": market,
        "tasks": [tasks_payload] if tasks_payload else [],
        "target_groups": [groups_payload] if groups_payload else [],
        "battlefields": [battlefields_payload] if battlefields_payload else [],
        "semantic_market": semantic_market,
        "source_refs": _v4_dedupe_evidence_refs(refs),
    }
    return SkuEvidenceSnapshot(**payload, snapshot_hash=canonical_v4_hash(payload))


def _v4_profile_ref_for_module(module_code: str, row: Any) -> EvidenceRef:
    config = {
        "M03B": ("core3_sku_param_profile", "sku_param_profile_id", "profile_hash"),
        "M04C": ("core3_sku_claim_fact_profile", "claim_profile_id", "profile_hash"),
        "M05C": ("core3_sku_comment_fact_profile", "comment_profile_id", "profile_hash"),
        "M07": ("core3_sku_market_profile", "profile_id", "result_hash"),
        "M09C": ("core3_m09c_sku_user_task_profile", "profile_id", "profile_hash"),
        "M10C": ("core3_m10c_sku_target_group_profile", "profile_id", "profile_hash"),
        "M11C": ("core3_sku_value_battlefield_profile", "profile_id", "profile_hash"),
    }[module_code]
    return _v4_row_evidence_ref(
        module_code,
        row,
        record_type=config[0],
        record_id_attr=config[1],
        result_hash_attr=config[2],
    )


def _v4_sku_identity(
    *,
    sku_code: str,
    market: Any | None,
    param: Any | None,
    target_fallback: ResolvedSku | None,
    candidate_ref: dict[str, Any] | None,
    product_category: str,
) -> SkuIdentity:
    param_values = (param.param_values_json or {}) if param is not None else {}
    screen_size = _number(market.screen_size_inch) if market is not None else None
    if screen_size is None:
        screen_size = _number(((param_values.get("dimension_tier_profile") or {}).get("screen_size_inch")))
    if screen_size is None and target_fallback is not None:
        screen_size = _number(target_fallback.screen_size_inch)
    return SkuIdentity(
        sku_code=sku_code,
        brand_name=(market.brand_name or market.brand) if market is not None else (candidate_ref or {}).get("brand_name") or (target_fallback.brand_name if target_fallback else None),
        model_name=(market.model_name if market is not None else None) or (param.model_name if param is not None else None) or (candidate_ref or {}).get("model_name") or (target_fallback.model_name if target_fallback else None),
        product_category=product_category,
        screen_size_inch=screen_size,
        size_tier=(market.size_segment if market is not None else None) or _param_size_tier(param) or (target_fallback.size_tier if target_fallback else None),
        price_band=(market.price_band_size if market is not None else None) or (target_fallback.price_band_in_size_tier if target_fallback else None),
    )


def _v4_trim_market_weekly_rows(
    rows: Sequence[entities.Core3CleanMarketWeekly],
    *,
    limit: int,
) -> tuple[list[entities.Core3CleanMarketWeekly], bool]:
    """Keep newest complete week/platform/channel groups within the row budget."""

    ordered = sorted(
        rows,
        key=lambda row: (
            -int(row.period_week_index),
            str(row.platform_type or ""),
            str(row.channel_type or ""),
            str(row.sku_code),
            str(row.source_row_id),
        ),
    )
    truncated = len(ordered) > limit
    if not truncated:
        return sorted(ordered, key=_v4_weekly_output_sort_key), False
    boundary_key = _v4_weekly_group_key(ordered[-1])
    complete_prefix = [
        row for row in ordered if _v4_weekly_group_key(row) != boundary_key
    ]
    selected: list[entities.Core3CleanMarketWeekly] = []
    for _, group in groupby(complete_prefix, key=_v4_weekly_group_key):
        group_rows = list(group)
        if len(selected) + len(group_rows) > limit:
            break
        selected.extend(group_rows)
    return sorted(selected, key=_v4_weekly_output_sort_key), True


def _v4_weekly_group_key(row: entities.Core3CleanMarketWeekly) -> tuple[int, str, str]:
    return (
        int(row.period_week_index),
        str(row.platform_type or ""),
        str(row.channel_type or ""),
    )


def _v4_weekly_output_sort_key(
    row: entities.Core3CleanMarketWeekly,
) -> tuple[int, str, str, str, str]:
    return (
        int(row.period_week_index),
        str(row.platform_type or ""),
        str(row.channel_type or ""),
        str(row.sku_code),
        str(row.source_row_id),
    )


def _v4_market_cells(
    *,
    weekly_rows: Sequence[entities.Core3CleanMarketWeekly],
    market_profiles: dict[str, entities.Core3SkuMarketProfile],
    battlefield_profiles: dict[str, entities.Core3SkuValueBattlefieldProfile],
    allocation_rows: Sequence[entities.Core3SemanticMarketAllocation],
) -> list[MarketCellRow]:
    allocation_weight = {
        (str(row.sku_code), str(row.dimension_code)): _number(row.allocation_weight)
        for row in allocation_rows
        if str(row.dimension_type) == "value_battlefield"
    }
    result: list[MarketCellRow] = []
    for row in weekly_rows:
        sku_code = str(row.sku_code)
        market = market_profiles.get(sku_code)
        battlefield = battlefield_profiles.get(sku_code)
        battlefield_code = str(battlefield.primary_battlefield_code or "unknown") if battlefield is not None else "unknown"
        result.append(
            MarketCellRow(
                sku_code=sku_code,
                battlefield_code=battlefield_code,
                period_week_index=int(row.period_week_index),
                platform_type=row.platform_type or "unknown",
                channel_type=row.channel_type,
                avg_price=_number(row.avg_price),
                sales_volume=_number(row.sales_volume),
                sales_amount=_number(row.sales_amount),
                battlefield_allocation_weight=allocation_weight.get((sku_code, battlefield_code)),
                value_bundle_tiers={},
                other_bundle_tiers={},
                brand_name=row.brand_name or (market.brand_name if market is not None else None),
                series_name=market.series if market is not None else None,
                price_check_status=str(row.price_check_status),
                promotion_suspect=bool(market.promotion_suspect_flag) if market is not None else False,
                inventory_status="unavailable",
                quality_flags=list(row.quality_flags or []),
                source_ref=EvidenceRef(
                    module_code="M07",
                    record_type="core3_clean_market_weekly",
                    record_id=str(row.clean_market_id),
                    result_hash=str(row.clean_hash),
                    batch_id=str(row.batch_id),
                    rule_version=str(row.clean_version),
                    evidence_ids=[str(row.source_row_id)],
                ),
            )
        )
    return result


def _v4_dedupe_evidence_refs(refs: Sequence[EvidenceRef]) -> list[EvidenceRef]:
    result: list[EvidenceRef] = []
    seen: set[tuple[str, str, str, str]] = set()
    for ref in refs:
        key = (ref.module_code, ref.record_type, ref.record_id, ref.result_hash)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return sorted(result, key=lambda ref: (ref.module_code, ref.record_type, ref.record_id, ref.result_hash))


def format_serving_scope_batch_id(product_category: str, batch_ids: Sequence[str]) -> str:
    normalized_category = str(product_category or "").upper()
    ordered_batch_ids = [str(batch_id).strip() for batch_id in batch_ids if str(batch_id).strip()]
    return f"{SERVING_SCOPE_BATCH_ID_PREFIX}{normalized_category}:{','.join(ordered_batch_ids)}"


def batch_ids_from_scope(batch_id: str) -> tuple[str, ...]:
    text = str(batch_id or "").strip()
    if not text.startswith(SERVING_SCOPE_BATCH_ID_PREFIX):
        return (text,) if text else ()
    _, _, raw_batch_ids = text.removeprefix(SERVING_SCOPE_BATCH_ID_PREFIX).partition(":")
    return tuple(batch_id for batch_id in (item.strip() for item in raw_batch_ids.split(",")) if batch_id)


def _batch_filter(column: Any, batch_id: str) -> Any:
    batch_ids = batch_ids_from_scope(batch_id)
    if len(batch_ids) == 1:
        return column == batch_ids[0]
    return column.in_(batch_ids)


def _batch_order_expr(column: Any, batch_id: str) -> Any:
    batch_ids = batch_ids_from_scope(batch_id)
    order_map = {candidate_batch_id: index for index, candidate_batch_id in enumerate(batch_ids)}
    return case(order_map, value=column, else_=len(batch_ids))


def unique_skus(candidates: Sequence[ResolvedSku]) -> list[ResolvedSku]:
    seen: set[str] = set()
    result: list[ResolvedSku] = []
    for candidate in candidates:
        if candidate.sku_code in seen:
            continue
        seen.add(candidate.sku_code)
        result.append(candidate)
    return result


def _claim_rule_version(product_category: str) -> str:
    return CORE3_M04C_AC_RULE_VERSION if str(product_category).upper() == "AC" else CORE3_M04C_TV_RULE_VERSION


def _comment_rule_version(product_category: str) -> str:
    return CORE3_M05C_AC_RULE_VERSION if str(product_category).upper() == "AC" else CORE3_M05C_TV_RULE_VERSION


def _user_task_rule_version(product_category: str) -> str:
    return CORE3_M09C_AC_RULE_VERSION if str(product_category).upper() == "AC" else CORE3_M09C_TV_RULE_VERSION


def _target_group_rule_version(product_category: str) -> str:
    return CORE3_M10C_AC_RULE_VERSION if str(product_category).upper() == "AC" else CORE3_M10C_TV_RULE_VERSION


def _battlefield_rule_version(product_category: str) -> str:
    return CORE3_M11C_AC_RULE_VERSION if str(product_category).upper() == "AC" else CORE3_M11C_TV_RULE_VERSION


def _m12c_rule_version(product_category: str) -> str:
    return CORE3_M12C_AC_RULE_VERSION if str(product_category).upper() == "AC" else CORE3_M12C_TV_RULE_VERSION


def _sellpoint_m12c_population(product_category: str, analysis_population: str) -> str:
    if str(product_category).upper() == "AC":
        return _m12c_population(analysis_population)
    return analysis_population


def _m11c_comparable_market_context(row: entities.Core3SkuValueBattlefieldScore | None) -> dict[str, Any]:
    if row is None:
        return {}
    score_breakdown = row.score_breakdown_json or {}
    market = score_breakdown.get("market") if isinstance(score_breakdown, dict) else {}
    context = market.get("comparable_market_context") if isinstance(market, dict) else {}
    return context if isinstance(context, dict) else {}


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
            "amount_percentile_in_size": _number(row.amount_percentile_in_size),
            "same_pool_price_percentile": _number(row.same_pool_price_percentile),
            "same_pool_volume_percentile": _number(row.same_pool_volume_percentile),
            "same_pool_amount_percentile": _number(row.same_pool_amount_percentile),
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


def _sellpoint_competitor_selection_payload(row: entities.Core3CompetitorSelection) -> dict[str, Any]:
    return {
        "sku_code": row.candidate_sku_code,
        "brand_name": row.candidate_brand_name,
        "model_name": row.candidate_model_name,
        "selection_rank": row.selection_rank,
        "slot_code": row.slot_code,
        "slot_name_cn": row.slot_name_cn,
        "selection_confidence": _number(row.confidence),
        "evidence_completeness_score": _number(row.evidence_completeness_score),
        "selection_source": "M14",
        "selection_evidence_ids": list(row.evidence_ids or []),
    }


def _sellpoint_comment_atom_payload(row: entities.Core3CommentFactAtom) -> dict[str, Any]:
    return {
        "source_comment_key": row.source_comment_key,
        "source_comment_id": row.source_comment_id,
        "sentence_seq": row.sentence_seq,
        "clean_comment_text": row.clean_comment_text,
        "dimension_code": row.dimension_code,
        "subdimension_code": row.subdimension_code,
        "dimension_type": row.dimension_type,
        "polarity": row.polarity,
        "support_relation": row.support_relation,
        "supported_param_codes": list(row.supported_param_codes or []),
        "contradicted_param_codes": list(row.contradicted_param_codes or []),
        "supported_claim_codes": list(row.supported_claim_codes or []),
        "contradicted_claim_codes": list(row.contradicted_claim_codes or []),
        "evidence_ids": list(row.evidence_ids or []),
        "quality_flags": list(row.quality_flags or []),
        "confidence": _number(row.confidence) or 0.0,
    }


def _sellpoint_market_weekly_payload(row: entities.Core3CleanMarketWeekly) -> dict[str, Any]:
    return {
        "sku_code": str(row.sku_code or ""),
        "period_week_index": int(row.period_week_index or 0),
        "period_raw": row.period_raw,
        "platform_type": row.platform_type or "unknown",
        "channel_type": row.channel_type,
        "sales_volume": _number(row.sales_volume),
        "sales_amount": _number(row.sales_amount),
        "avg_price": _number(row.avg_price),
        "price_check_status": row.price_check_status,
        "quality_flags": list(row.quality_flags or []),
        "evidence_ids": [row.clean_market_id, row.source_row_id],
    }


def _dedupe_texts(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


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
    supporting_dimensions = row.supporting_dimensions_json or {}
    scorecard = supporting_dimensions.get("scorecard") if isinstance(supporting_dimensions.get("scorecard"), dict) else {}
    business_claim_type = str(supporting_dimensions.get("business_claim_type") or _m12c_business_claim_type(row.claim_value_role, pool_price_delta))
    business_claim_type_cn = str(supporting_dimensions.get("business_claim_type_cn") or _m12c_business_claim_type_label(business_claim_type))
    target_has_claim = bool(supporting_dimensions.get("target_has_claim")) if "target_has_claim" in supporting_dimensions else _m12c_target_has_claim(row)
    claim_source_type = str(
        supporting_dimensions.get("claim_source_type")
        or _m12c_claim_source_type(target_has_claim=target_has_claim, business_claim_type_cn=business_claim_type_cn)
    )
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "claim_code": row.claim_code,
        "claim_name": row.claim_name,
        "claim_dimension": row.claim_dimension,
        "claim_value_role": row.claim_value_role,
        "business_claim_type": business_claim_type,
        "business_claim_type_cn": business_claim_type_cn,
        "business_claim_type_definition_cn": supporting_dimensions.get("business_claim_type_definition_cn") or _m12c_business_claim_type_meaning_cn(business_claim_type),
        "target_has_claim": target_has_claim,
        "claim_source_type": claim_source_type,
        "claim_source_type_cn": _m12c_claim_source_type_label(claim_source_type),
        "claim_value_score": supporting_dimensions.get("claim_value_score") or scorecard.get("total_score"),
        "parameter_competitiveness": supporting_dimensions.get("parameter_competitiveness") or {},
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
        "scorecard": scorecard,
        "market_position": {
            "type": supporting_dimensions.get("market_position_type"),
            "summary_cn": supporting_dimensions.get("market_position_cn"),
        },
        "supporting_dimensions": supporting_dimensions,
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


def _sku_level_claim_value_summary(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    battlefield_rows = [row for row in rows if str(row.get("context_type") or "") == "battlefield"]
    source_rows = battlefield_rows or list(rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in source_rows:
        claim_key = str(row.get("claim_code") or row.get("claim_name") or "")
        if not claim_key:
            continue
        grouped.setdefault(claim_key, []).append(row)
    result: list[dict[str, Any]] = []
    for claim_key, claim_rows in grouped.items():
        context_rows = _dedupe_sku_level_claim_context_rows(claim_rows)
        business_claim_type_cn = _best_m12c_business_claim_type_cn(context_rows)
        target_has_claim = any(_m12c_payload_target_has_claim(row) for row in context_rows)
        claim_source_type = _best_m12c_claim_source_type(context_rows, target_has_claim=target_has_claim, business_claim_type_cn=business_claim_type_cn)
        price_total = sum(_decimal(((row.get("estimated_contribution") or {}).get("price_premium_abs")) or 0) or Decimal("0") for row in context_rows)
        sales_total = sum(_decimal(((row.get("estimated_contribution") or {}).get("weekly_sales_lift_abs")) or 0) or Decimal("0") for row in context_rows)
        amount_total = sum(_decimal(((row.get("estimated_contribution") or {}).get("weekly_sales_amount_lift_abs")) or 0) or Decimal("0") for row in context_rows)
        score = _m12c_aggregate_score(context_rows)
        result.append(
            {
                "claim_code": claim_key,
                "claim_name": str(context_rows[0].get("claim_name") or claim_key),
                "business_claim_type_cn": business_claim_type_cn,
                "business_claim_type": str(context_rows[0].get("business_claim_type") or _m12c_business_claim_type_from_cn(business_claim_type_cn)),
                "target_has_claim": target_has_claim,
                "claim_source_type": claim_source_type,
                "claim_source_type_cn": _m12c_claim_source_type_label(claim_source_type),
                "sku_level_user_payment_value_abs": _number(price_total),
                "sku_level_weekly_sales_lift_abs": _number(sales_total),
                "sku_level_weekly_sales_amount_lift_abs": _number(amount_total),
                "claim_value_score": _number(score),
                "parameter_competitiveness": _best_m12c_parameter_competitiveness(context_rows),
                "main_contexts": _unique_nonempty(row.get("context_name") or row.get("context_code") for row in context_rows),
                "evidence_summary_cn": _sku_level_claim_evidence_summary(context_rows),
                "context_values": [
                    {
                        "context_type": row.get("context_type"),
                        "context_code": row.get("context_code"),
                        "context_name": row.get("context_name"),
                        "business_claim_type_cn": row.get("business_claim_type_cn") or _m12c_business_claim_type_label(_m12c_business_claim_type(row.get("claim_value_role"), ((row.get("pool_effect") or {}).get("pool_claim_price_delta_abs")))),
                        "claim_value_score": row.get("claim_value_score"),
                        "price_premium_abs": ((row.get("estimated_contribution") or {}).get("price_premium_abs")),
                        "weekly_sales_lift_abs": ((row.get("estimated_contribution") or {}).get("weekly_sales_lift_abs")),
                        "weekly_sales_amount_lift_abs": ((row.get("estimated_contribution") or {}).get("weekly_sales_amount_lift_abs")),
                        "pool_effect": row.get("pool_effect") or {},
                        "scorecard": row.get("scorecard") or {},
                        "unique_payment_potential_scorecard": (row.get("supporting_dimensions") or {}).get("unique_payment_potential_scorecard") or (row.get("scorecard") or {}).get("unique_payment_potential") or {},
                        "parameter_competitiveness": row.get("parameter_competitiveness") or {},
                        "quality_flags": row.get("quality_flags") or [],
                        "target_has_claim": _m12c_payload_target_has_claim(row),
                        "claim_source_type_cn": row.get("claim_source_type_cn") or _m12c_claim_source_type_label(str(row.get("claim_source_type") or claim_source_type)),
                    }
                    for row in context_rows[:8]
                ],
            }
        )
    return sorted(result, key=_sku_level_claim_sort_key)


def _dedupe_sku_level_claim_context_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("context_type") or ""),
            str(row.get("context_code") or row.get("context_name") or ""),
            str(row.get("business_claim_type_cn") or _m12c_business_claim_type_label(_m12c_business_claim_type(row.get("claim_value_role"), ((row.get("pool_effect") or {}).get("pool_claim_price_delta_abs"))))),
        )
        existing = deduped.get(key)
        if existing is None or _sku_level_claim_row_strength(row) > _sku_level_claim_row_strength(existing):
            deduped[key] = row
    return list(deduped.values())


def _sku_level_claim_row_strength(row: Mapping[str, Any]) -> Decimal:
    estimated = row.get("estimated_contribution") or {}
    score = _decimal(row.get("claim_value_score")) or Decimal("0")
    amount = _decimal(estimated.get("weekly_sales_amount_lift_abs")) or Decimal("0")
    price = _decimal(estimated.get("price_premium_abs")) or Decimal("0")
    return score + max(amount, Decimal("0")) / Decimal("100000") + max(price, Decimal("0")) / Decimal("100")


def _best_m12c_business_claim_type_cn(rows: Sequence[dict[str, Any]]) -> str:
    if not rows:
        return "未分类卖点"
    return min((_m12c_business_claim_type_cn(row) for row in rows), key=lambda label: M12C_BUSINESS_CLAIM_TYPE_PRIORITY.get(label, 99))


def _m12c_business_claim_type_cn(row: Mapping[str, Any]) -> str:
    label = str(row.get("business_claim_type_cn") or "").strip()
    if label:
        return label
    return _m12c_business_claim_type_label(_m12c_business_claim_type(row.get("claim_value_role"), ((row.get("pool_effect") or {}).get("pool_claim_price_delta_abs"))))


def _m12c_aggregate_score(rows: Sequence[dict[str, Any]]) -> Decimal:
    values = [_decimal(row.get("claim_value_score")) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        strengths: list[Decimal] = []
        for row in rows:
            evidence = row.get("evidence_strength") or {}
            for key in ("param", "comment", "semantic"):
                value = _decimal(evidence.get(key))
                if value is not None:
                    strengths.append(value * Decimal("100"))
        return _avg_decimal(strengths) or Decimal("0")
    return _avg_decimal(values) or Decimal("0")


def _sku_level_claim_evidence_summary(rows: Sequence[dict[str, Any]]) -> str:
    if not rows:
        return ""
    best = max(rows, key=_sku_level_claim_row_strength)
    evidence = best.get("evidence_strength") or {}
    parts: list[str] = []
    parameter_competitiveness = _best_m12c_parameter_competitiveness(rows)
    parameter_label = str(parameter_competitiveness.get("overall_parameter_competitiveness_level_cn") or "").strip()
    if parameter_label:
        parts.append(f"参数竞争力{parameter_label}")
    param = _decimal(evidence.get("param"))
    comment = _decimal(evidence.get("comment"))
    semantic = _decimal(evidence.get("semantic"))
    if param is not None and not parameter_label:
        parts.append("参数强" if param >= Decimal("0.75") else "参数中等" if param >= Decimal("0.45") else "参数弱")
    if comment is not None:
        parts.append("评论强" if comment >= Decimal("0.75") else "评论中等" if comment >= Decimal("0.45") else "评论弱")
    if semantic is not None:
        parts.append("战场相关强" if semantic >= Decimal("0.75") else "战场相关中等" if semantic >= Decimal("0.45") else "战场相关弱")
    evidence_text = "、".join(parts) if parts else "证据待补充"
    return f"证据结构：{evidence_text}。"


def _best_m12c_parameter_competitiveness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    snapshots = [row.get("parameter_competitiveness") for row in rows if isinstance(row.get("parameter_competitiveness"), dict)]
    snapshots = [dict(item) for item in snapshots if item]
    if not snapshots:
        return {}
    return max(snapshots, key=lambda item: float(_decimal(item.get("overall_parameter_competitiveness_score")) or Decimal("0")))


def _best_m12c_claim_source_type(rows: Sequence[Mapping[str, Any]], *, target_has_claim: bool, business_claim_type_cn: str) -> str:
    source_types = [str(row.get("claim_source_type") or "").strip() for row in rows if str(row.get("claim_source_type") or "").strip()]
    if "target_fact_claim" in source_types:
        return "target_fact_claim"
    if "target_param_capability" in source_types:
        return "target_param_capability"
    if "competitor_opportunity_gap" in source_types:
        return "competitor_opportunity_gap"
    return _m12c_claim_source_type(target_has_claim=target_has_claim, business_claim_type_cn=business_claim_type_cn)


def _sku_level_claim_sort_key(item: Mapping[str, Any]) -> tuple[int, float, float, str]:
    label = str(item.get("business_claim_type_cn") or "")
    price = float(_decimal(item.get("sku_level_user_payment_value_abs")) or Decimal("0"))
    score = float(_decimal(item.get("claim_value_score")) or Decimal("0"))
    return (M12C_BUSINESS_CLAIM_TYPE_PRIORITY.get(label, 99), -price, -score, str(item.get("claim_name") or ""))


def _m12c_target_has_claim(row: entities.Core3SkuClaimValueQuantification) -> bool:
    evidence_count = len(row.evidence_ids_json or [])
    claim_strength = _decimal(row.claim_evidence_strength) or Decimal("0")
    return evidence_count > 0 and claim_strength > 0


def _m12c_payload_target_has_claim(row: Mapping[str, Any]) -> bool:
    if "target_has_claim" in row:
        return bool(row.get("target_has_claim"))
    evidence = row.get("evidence_strength") or {}
    claim_strength = _decimal(evidence.get("claim")) or Decimal("0")
    evidence_count = row.get("evidence_id_count")
    try:
        evidence_count_int = int(evidence_count or 0)
    except (TypeError, ValueError):
        evidence_count_int = 0
    return evidence_count_int > 0 and claim_strength > 0


def _m12c_claim_source_type(*, target_has_claim: bool, business_claim_type_cn: str) -> str:
    if target_has_claim:
        return "target_fact_claim"
    if business_claim_type_cn == "竞品拦截卖点":
        return "competitor_opportunity_gap"
    return "non_target_signal"


def _m12c_claim_source_type_label(source_type: str) -> str:
    return {
        "target_fact_claim": "本品已成立卖点",
        "target_param_capability": "本品参数能力待激活",
        "competitor_opportunity_gap": "竞品拦截/机会缺口",
        "non_target_signal": "非本品已成立卖点",
    }.get(str(source_type or ""), "来源待确认")


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
    if role == M12C_ROLE_UNIQUE:
        return "人无我有型支付价值卖点"
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
    if role == M12C_ROLE_UNIQUE:
        return "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿；当前对照样本不足，只输出潜力和证据链，不输出金额。"
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


def _m12c_business_claim_type(role: Any, pool_price_delta: Any = None) -> str:
    price_delta = _decimal(pool_price_delta) or Decimal("0")
    role = str(role or "")
    if role == M12C_ROLE_PREMIUM:
        return "premium_payment_claim" if price_delta > 0 else "customer_value_claim"
    if role == M12C_ROLE_SALES:
        return "share_conversion_claim"
    if role == M12C_ROLE_VALUE_BUNDLE:
        return "customer_value_claim"
    if role == M12C_ROLE_UNIQUE:
        return "unique_payment_potential_claim"
    if role == M12C_ROLE_BASIC:
        return "threshold_claim"
    if role in {M12C_ROLE_WEAK_USER, M12C_ROLE_USER_NEED}:
        return "pending_activation_claim"
    if role == M12C_ROLE_BRAND:
        return "brand_claim"
    if role in {M12C_ROLE_HIGH_PRICE_INTERCEPT, M12C_ROLE_PRICE_UP, M12C_ROLE_OPPORTUNITY}:
        return "competitor_intercept_claim"
    if role == M12C_ROLE_DRAG:
        return "price_pressure_claim"
    return "sample_insufficient_claim"


def _m12c_business_claim_type_label(claim_type: str) -> str:
    return {
        "premium_payment_claim": "高溢价卖点",
        "share_conversion_claim": "份额转化卖点",
        "customer_value_claim": "客户获得价值卖点",
        "threshold_claim": "门槛卖点",
        "pending_activation_claim": "待激活卖点",
        "brand_claim": "厂家主张卖点",
        "competitor_intercept_claim": "竞品拦截卖点",
        "price_pressure_claim": "价格压力卖点",
        "sample_insufficient_claim": "样本不足待复核",
        "unique_payment_potential_claim": "人无我有型支付价值卖点",
    }.get(str(claim_type or ""), "未分类卖点")


def _m12c_business_claim_type_from_cn(label: str) -> str:
    reverse = {
        "高溢价卖点": "premium_payment_claim",
        "份额转化卖点": "share_conversion_claim",
        "客户获得价值卖点": "customer_value_claim",
        "门槛卖点": "threshold_claim",
        "待激活卖点": "pending_activation_claim",
        "厂家主张卖点": "brand_claim",
        "竞品拦截卖点": "competitor_intercept_claim",
        "价格压力卖点": "price_pressure_claim",
        "样本不足待复核": "sample_insufficient_claim",
        "人无我有型支付价值卖点": "unique_payment_potential_claim",
    }
    return reverse.get(str(label or ""), "sample_insufficient_claim")


def _m12c_business_claim_type_meaning_cn(claim_type: str) -> str:
    return {
        "premium_payment_claim": "用户愿意为该卖点支付更高价格，并且参数、评论和市场验证共同成立。",
        "share_conversion_claim": "该卖点不一定抬高价格，但能解释同价或相近价格下的销量/份额优势。",
        "customer_value_claim": "该卖点让用户觉得产品更值，主要体现为价格压力更小或销量承接更强。",
        "threshold_claim": "该卖点是进入购买清单的基础要求，有了不加价，缺了会掉队。",
        "pending_activation_claim": "本品有参数或厂家表达，但用户评论或市场验证还不足，需要继续激活。",
        "brand_claim": "当前主要是厂家主张，尚未形成稳定用户支付价值。",
        "competitor_intercept_claim": "竞品具备并形成市场验证，本品缺失或表达弱，会影响购买转化。",
        "price_pressure_claim": "卖点表达、参数或用户反馈没有支撑当前价格，可能削弱成交理由。",
        "sample_insufficient_claim": "样本或对照组不足，只能作为观察线索。",
        "unique_payment_potential_claim": "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿，但当前缺少稳定对照样本，不能量化金额。",
    }.get(str(claim_type or ""), "当前分类尚未定义。")


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


def _unique_nonempty(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
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


def _known_value(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return bool(text and text not in {"-", "unknown", "none", "null", "nan"})


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
