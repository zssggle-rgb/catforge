"""Extract business-facing publish rows from persisted CatForge results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_repository import AnalystRepository
from app.services.core3_real_data.constants import (
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_AC_RULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M10C_AC_RULE_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11D_RULE_VERSION,
    CORE3_M12C_RULE_VERSION,
    CORE3_M14_RULE_VERSION,
)
from app.services.core3_real_data.publish.base_schema import (
    ANALYSIS_BATCH,
    BATTLEFIELD_MAP,
    CLAIM_VALUE,
    COMPETITOR_RELATIONS,
    SKU_OVERVIEW,
)


PRODUCT_CATEGORY_CN = {"tv": "彩电", "TV": "彩电", "ac": "空调", "AC": "空调"}

CLAIM_ROLE_CN = {
    "premium_driver_estimated": "高溢价卖点",
    "sales_driver_estimated": "份额转化卖点",
    "value_bundle_claim": "客户获得价值卖点",
    "unique_payment_potential": "人无我有型支付价值卖点",
    "basic_threshold": "门槛卖点",
    "weak_user_perception_claim": "待激活卖点",
    "brand_claim_only": "厂家主张卖点",
    "competitor_intercept": "竞品拦截卖点",
    "opportunity_gap": "竞品拦截卖点",
    "high_price_competitor_intercept": "竞品拦截卖点",
    "price_pressure": "价格压力卖点",
    "drag_factor": "价格压力卖点",
    "sample_insufficient": "样本不足待复核",
}


class PublishExtractors:
    """Read published rows from stable result tables without recalculating analysis."""

    def __init__(
        self,
        db: Session,
        *,
        project_id: str,
        category_code: str,
        product_category: str = "tv",
        market_window: str = "full_observed_window",
        analysis_population: str = "fact_complete_with_comment",
        claim_analysis_population: str = "claim_value_ready_with_comment",
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = category_code.upper()
        self.product_category = product_category
        self.market_window = market_window
        self.analysis_population = analysis_population
        self.claim_analysis_population = claim_analysis_population

    def resolve_batch_id(self, batch_id: str) -> str:
        if batch_id != "latest":
            return batch_id
        latest = AnalystRepository(self.db, project_id=self.project_id, category_code=self.category_code).latest_batch_id()
        if not latest:
            raise RuntimeError("未找到可发布的最新分析批次。")
        return latest

    def extract(self, scope: str, *, batch_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        resolved_batch_id = self.resolve_batch_id(batch_id)
        if scope == ANALYSIS_BATCH:
            return self.extract_analysis_batch(batch_id=resolved_batch_id)
        if scope == SKU_OVERVIEW:
            return self.extract_sku_overview(batch_id=resolved_batch_id, limit=limit)
        if scope == BATTLEFIELD_MAP:
            return self.extract_battlefield_map(batch_id=resolved_batch_id, limit=limit)
        if scope == COMPETITOR_RELATIONS:
            return self.extract_competitor_relations(batch_id=resolved_batch_id, limit=limit)
        if scope == CLAIM_VALUE:
            return self.extract_claim_value(batch_id=resolved_batch_id, limit=limit)
        raise ValueError(f"unknown publish scope: {scope}")

    def extract_analysis_batch(self, *, batch_id: str) -> list[dict[str, Any]]:
        batch = self.db.execute(
            select(entities.Core3SourceBatch)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code)
            .where(entities.Core3SourceBatch.batch_id == batch_id)
        ).scalar_one_or_none()
        sku_count = self._count(entities.Core3SkuMarketProfile, batch_id=batch_id, rule_version=CORE3_M07_RULE_VERSION)
        comment_sku_count = self._count(entities.Core3SkuCommentFactProfile, batch_id=batch_id)
        competitor_count = self._count(entities.Core3CompetitorSelection, batch_id=batch_id, rule_version=CORE3_M14_RULE_VERSION)
        claim_value_count = self._count(entities.Core3SkuClaimValueQuantification, batch_id=batch_id, rule_version=CORE3_M12C_RULE_VERSION)
        return [
            {
                "batch_id": batch_id,
                "category_code": self.category_code,
                "product_category": PRODUCT_CATEGORY_CN.get(self.product_category, self.product_category),
                "data_window": _data_window(batch),
                "source_batch_id": batch_id,
                "sku_count": sku_count,
                "comment_sku_count": comment_sku_count,
                "sku_overview_count": sku_count,
                "competitor_relation_count": competitor_count,
                "claim_value_count": claim_value_count,
                "sync_status": "同步中",
                "synced_at": _now(),
                "note_cn": _batch_note(batch),
            }
        ]

    def extract_sku_overview(self, *, batch_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        market_rows = self.db.execute(
            _limit(
                select(entities.Core3SkuMarketProfile)
                .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
                .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
                .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
                .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
                .where(entities.Core3SkuMarketProfile.is_current.is_(True))
                .order_by(entities.Core3SkuMarketProfile.brand_name, entities.Core3SkuMarketProfile.model_name),
                limit,
            )
        ).scalars().all()
        sku_codes = [row.sku_code for row in market_rows]
        task_names = self._primary_task_names(batch_id=batch_id, sku_codes=sku_codes)
        group_names = self._primary_group_names(batch_id=batch_id, sku_codes=sku_codes)
        battlefield_names = self._primary_battlefield_names(batch_id=batch_id, sku_codes=sku_codes)
        claim_summaries = self._top_claim_summaries(batch_id=batch_id, sku_codes=sku_codes)
        competitor_urls = self._report_urls(batch_id=batch_id, export_type_keywords=("competitor", "竞品"))
        claim_urls = self._report_urls(batch_id=batch_id, export_type_keywords=("claim", "卖点"))
        records: list[dict[str, Any]] = []
        for row in market_rows:
            weeks = max(int(row.active_week_count or 0), 1)
            records.append(
                {
                    "batch_id": batch_id,
                    "category_code": self.category_code,
                    "sku_code": row.sku_code,
                    "brand_name": row.brand_name or row.brand,
                    "model_name": row.model_name,
                    "screen_size_inch": _number(row.screen_size_inch),
                    "size_tier": row.size_segment or "unknown",
                    "price_band": row.price_band_size or "unknown",
                    "weighted_price": _number(row.price_wavg),
                    "avg_weekly_sales_volume": _round(_number(row.sales_volume_total) / weeks if row.sales_volume_total is not None else None, 0),
                    "avg_weekly_sales_amount": _round(_number(row.sales_amount_total) / weeks if row.sales_amount_total is not None else None, 1),
                    "primary_battlefield": battlefield_names.get(row.sku_code),
                    "primary_user_task": task_names.get(row.sku_code),
                    "primary_target_group": group_names.get(row.sku_code),
                    "top_claims_cn": claim_summaries.get(row.sku_code),
                    "competitor_report_url": competitor_urls.get(row.sku_code),
                    "claim_value_report_url": claim_urls.get(row.sku_code),
                    "updated_at": row.updated_at,
                }
            )
        return records

    def extract_battlefield_map(self, *, batch_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self.db.execute(
            _limit(
                select(entities.Core3SemanticMarketDimensionSummary)
                .where(entities.Core3SemanticMarketDimensionSummary.project_id == self.project_id)
                .where(entities.Core3SemanticMarketDimensionSummary.category_code == self.category_code)
                .where(entities.Core3SemanticMarketDimensionSummary.batch_id == batch_id)
                .where(entities.Core3SemanticMarketDimensionSummary.dimension_type == "battlefield")
                .where(entities.Core3SemanticMarketDimensionSummary.analysis_population == self.analysis_population)
                .where(entities.Core3SemanticMarketDimensionSummary.market_window == self.market_window)
                .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
                .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
                .order_by(desc(entities.Core3SemanticMarketDimensionSummary.estimated_avg_weekly_sales_amount)),
                limit,
            )
        ).scalars().all()
        records: list[dict[str, Any]] = []
        for row in rows:
            records.append(
                {
                    "batch_id": batch_id,
                    "category_code": self.category_code,
                    "battlefield_code": row.dimension_code,
                    "battlefield_name": row.dimension_name,
                    "size_tiers": _distribution_keys(row.size_price_distribution_json, "size_tier"),
                    "price_bands": _distribution_keys(row.size_price_distribution_json, "price_band"),
                    "covered_sku_count": row.allocated_sku_count or row.sku_relation_count,
                    "allocated_sales_volume": _round(_number(row.estimated_avg_weekly_sales_volume), 0),
                    "allocated_sales_amount": _round(_number(row.estimated_avg_weekly_sales_amount), 1),
                    "leading_brands_cn": _top_distribution(row.brand_distribution_json, label_keys=("brand_name", "brand")),
                    "representative_skus_cn": _top_skus(row.top_skus_json),
                    "business_summary_cn": row.business_summary_cn,
                    "updated_at": row.updated_at,
                }
            )
        return records

    def extract_competitor_relations(self, *, batch_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self.db.execute(
            _limit(
                select(entities.Core3CompetitorSelection)
                .where(entities.Core3CompetitorSelection.project_id == self.project_id)
                .where(entities.Core3CompetitorSelection.category_code == self.category_code)
                .where(entities.Core3CompetitorSelection.batch_id == batch_id)
                .where(entities.Core3CompetitorSelection.rule_version == CORE3_M14_RULE_VERSION)
                .where(entities.Core3CompetitorSelection.is_current.is_(True))
                .order_by(entities.Core3CompetitorSelection.target_model_name, entities.Core3CompetitorSelection.selection_rank),
                limit,
            )
        ).scalars().all()
        candidate_skus = {row.candidate_sku_code for row in rows}
        sales = self._market_sales_by_sku(batch_id=batch_id, sku_codes=candidate_skus)
        urls = self._report_urls(batch_id=batch_id, export_type_keywords=("competitor", "竞品"))
        records: list[dict[str, Any]] = []
        for row in rows:
            scores = row.component_scores_json or {}
            records.append(
                {
                    "batch_id": batch_id,
                    "category_code": self.category_code,
                    "target_sku_code": row.target_sku_code,
                    "target_brand": row.target_brand_name,
                    "target_model": row.target_model_name,
                    "competitor_sku_code": row.candidate_sku_code,
                    "competitor_brand": row.candidate_brand_name,
                    "competitor_model": row.candidate_model_name,
                    "rank": row.selection_rank,
                    "competitor_role_cn": _competitor_role_cn(row.slot_name_cn),
                    "same_purchase_pool_score": _score(scores, "same_purchase_pool", "same_purchase_pool_score", "purchase_pool_score"),
                    "battlefield_overlap_score": _score(scores, "battlefield_overlap", "battlefield_overlap_score", "value_battlefield_overlap_score"),
                    "user_task_overlap_score": _score(scores, "user_task_overlap", "user_task_overlap_score", "task_overlap_score"),
                    "target_group_overlap_score": _score(scores, "target_group_overlap", "target_group_overlap_score", "audience_overlap_score"),
                    "value_anchor_overlap_score": _score(scores, "value_anchor_overlap", "value_anchor_overlap_score", "claim_param_overlap_score"),
                    "replacement_pressure_cn": row.business_conclusion_cn or row.selection_reason_short_cn,
                    "avg_weekly_sales_volume": sales.get(row.candidate_sku_code),
                    "report_url": urls.get(row.target_sku_code),
                    "reasoning_cn": row.selection_reason_cn or row.selection_reason_short_cn,
                    "updated_at": row.updated_at,
                }
            )
        return records

    def extract_claim_value(self, *, batch_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self.db.execute(
            _limit(
                select(entities.Core3SkuClaimValueQuantification)
                .where(entities.Core3SkuClaimValueQuantification.project_id == self.project_id)
                .where(entities.Core3SkuClaimValueQuantification.category_code == self.category_code)
                .where(entities.Core3SkuClaimValueQuantification.batch_id == batch_id)
                .where(entities.Core3SkuClaimValueQuantification.market_window == self.market_window)
                .where(entities.Core3SkuClaimValueQuantification.analysis_population == self.claim_analysis_population)
                .where(entities.Core3SkuClaimValueQuantification.rule_version == CORE3_M12C_RULE_VERSION)
                .where(entities.Core3SkuClaimValueQuantification.is_current.is_(True))
                .order_by(
                    entities.Core3SkuClaimValueQuantification.sku_code,
                    desc(entities.Core3SkuClaimValueQuantification.estimated_price_premium_abs),
                    desc(entities.Core3SkuClaimValueQuantification.estimated_weekly_sales_lift_abs),
                ),
                limit,
            )
        ).scalars().all()
        urls = self._report_urls(batch_id=batch_id, export_type_keywords=("claim", "卖点"))
        records: list[dict[str, Any]] = []
        for row in rows:
            role_cn = CLAIM_ROLE_CN.get(row.claim_value_role, row.claim_value_role)
            records.append(
                {
                    "batch_id": batch_id,
                    "category_code": self.category_code,
                    "sku_code": row.sku_code,
                    "brand_name": row.brand_name,
                    "model_name": row.model_name,
                    "claim_code": row.claim_code,
                    "claim_name": row.claim_name,
                    "claim_role_cn": role_cn,
                    "explainable_price_value": _positive_number(row.estimated_price_premium_abs),
                    "explainable_weekly_sales": _positive_number(row.estimated_weekly_sales_lift_abs),
                    "main_battlefields_cn": _claim_context(row),
                    "parameter_evidence_cn": _support_text("参数", row.param_support_strength),
                    "comment_evidence_cn": _support_text("评论", row.comment_support_strength),
                    "market_validation_cn": row.reason_cn or _market_context(row),
                    "action_suggestion_cn": _claim_action(role_cn),
                    "report_url": urls.get(row.sku_code),
                    "confidence_cn": _confidence_label(row.attribution_confidence),
                    "updated_at": row.updated_at,
                }
            )
        return records

    def _count(self, model: Any, *, batch_id: str, rule_version: str | None = None) -> int:
        sku_column = getattr(model, "sku_code", None)
        count_expr = func.count(distinct(sku_column)) if sku_column is not None else func.count()
        stmt = (
            select(count_expr)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code)
            .where(model.batch_id == batch_id)
        )
        if hasattr(model, "is_current"):
            stmt = stmt.where(model.is_current.is_(True))
        if rule_version and hasattr(model, "rule_version"):
            stmt = stmt.where(model.rule_version == rule_version)
        return int(self.db.execute(stmt).scalar_one() or 0)

    def _primary_task_names(self, *, batch_id: str, sku_codes: list[str]) -> dict[str, str]:
        rule_version = _task_rule_version(self.product_category)
        scores = self.db.execute(
            select(entities.Core3M09cSkuUserTaskScore)
            .where(entities.Core3M09cSkuUserTaskScore.project_id == self.project_id)
            .where(entities.Core3M09cSkuUserTaskScore.category_code == self.category_code)
            .where(entities.Core3M09cSkuUserTaskScore.batch_id == batch_id)
            .where(entities.Core3M09cSkuUserTaskScore.rule_version == rule_version)
            .where(entities.Core3M09cSkuUserTaskScore.is_current.is_(True))
            .where(entities.Core3M09cSkuUserTaskScore.sku_code.in_(sku_codes or [""]))
        ).scalars()
        mapping: dict[tuple[str, str], str] = {(row.sku_code, row.user_task_code): row.user_task_name for row in scores}
        profiles = self.db.execute(
            select(entities.Core3M09cSkuUserTaskProfile)
            .where(entities.Core3M09cSkuUserTaskProfile.project_id == self.project_id)
            .where(entities.Core3M09cSkuUserTaskProfile.category_code == self.category_code)
            .where(entities.Core3M09cSkuUserTaskProfile.batch_id == batch_id)
            .where(entities.Core3M09cSkuUserTaskProfile.rule_version == rule_version)
            .where(entities.Core3M09cSkuUserTaskProfile.is_current.is_(True))
            .where(entities.Core3M09cSkuUserTaskProfile.sku_code.in_(sku_codes or [""]))
        ).scalars()
        return {row.sku_code: mapping.get((row.sku_code, row.primary_user_task_code), row.primary_user_task_code or "") for row in profiles}

    def _primary_group_names(self, *, batch_id: str, sku_codes: list[str]) -> dict[str, str]:
        rule_version = _group_rule_version(self.product_category)
        scores = self.db.execute(
            select(entities.Core3M10cSkuTargetGroupScore)
            .where(entities.Core3M10cSkuTargetGroupScore.project_id == self.project_id)
            .where(entities.Core3M10cSkuTargetGroupScore.category_code == self.category_code)
            .where(entities.Core3M10cSkuTargetGroupScore.batch_id == batch_id)
            .where(entities.Core3M10cSkuTargetGroupScore.rule_version == rule_version)
            .where(entities.Core3M10cSkuTargetGroupScore.is_current.is_(True))
            .where(entities.Core3M10cSkuTargetGroupScore.sku_code.in_(sku_codes or [""]))
        ).scalars()
        mapping: dict[tuple[str, str], str] = {(row.sku_code, row.target_group_code): row.target_group_name for row in scores}
        profiles = self.db.execute(
            select(entities.Core3M10cSkuTargetGroupProfile)
            .where(entities.Core3M10cSkuTargetGroupProfile.project_id == self.project_id)
            .where(entities.Core3M10cSkuTargetGroupProfile.category_code == self.category_code)
            .where(entities.Core3M10cSkuTargetGroupProfile.batch_id == batch_id)
            .where(entities.Core3M10cSkuTargetGroupProfile.rule_version == rule_version)
            .where(entities.Core3M10cSkuTargetGroupProfile.is_current.is_(True))
            .where(entities.Core3M10cSkuTargetGroupProfile.sku_code.in_(sku_codes or [""]))
        ).scalars()
        return {row.sku_code: mapping.get((row.sku_code, row.primary_target_group_code), row.primary_target_group_code or "") for row in profiles}

    def _primary_battlefield_names(self, *, batch_id: str, sku_codes: list[str]) -> dict[str, str]:
        rule_version = _battlefield_rule_version(self.product_category)
        scores = self.db.execute(
            select(entities.Core3SkuValueBattlefieldScore)
            .where(entities.Core3SkuValueBattlefieldScore.project_id == self.project_id)
            .where(entities.Core3SkuValueBattlefieldScore.category_code == self.category_code)
            .where(entities.Core3SkuValueBattlefieldScore.batch_id == batch_id)
            .where(entities.Core3SkuValueBattlefieldScore.rule_version == rule_version)
            .where(entities.Core3SkuValueBattlefieldScore.is_current.is_(True))
            .where(entities.Core3SkuValueBattlefieldScore.sku_code.in_(sku_codes or [""]))
        ).scalars()
        mapping: dict[tuple[str, str], str] = {(row.sku_code, row.battlefield_code): row.battlefield_name for row in scores}
        profiles = self.db.execute(
            select(entities.Core3SkuValueBattlefieldProfile)
            .where(entities.Core3SkuValueBattlefieldProfile.project_id == self.project_id)
            .where(entities.Core3SkuValueBattlefieldProfile.category_code == self.category_code)
            .where(entities.Core3SkuValueBattlefieldProfile.batch_id == batch_id)
            .where(entities.Core3SkuValueBattlefieldProfile.rule_version == rule_version)
            .where(entities.Core3SkuValueBattlefieldProfile.is_current.is_(True))
            .where(entities.Core3SkuValueBattlefieldProfile.sku_code.in_(sku_codes or [""]))
        ).scalars()
        return {row.sku_code: mapping.get((row.sku_code, row.primary_battlefield_code), row.primary_battlefield_code or "") for row in profiles}

    def _top_claim_summaries(self, *, batch_id: str, sku_codes: list[str]) -> dict[str, str]:
        rows = self.db.execute(
            select(entities.Core3SkuClaimValueQuantification)
            .where(entities.Core3SkuClaimValueQuantification.project_id == self.project_id)
            .where(entities.Core3SkuClaimValueQuantification.category_code == self.category_code)
            .where(entities.Core3SkuClaimValueQuantification.batch_id == batch_id)
            .where(entities.Core3SkuClaimValueQuantification.rule_version == CORE3_M12C_RULE_VERSION)
            .where(entities.Core3SkuClaimValueQuantification.is_current.is_(True))
            .where(entities.Core3SkuClaimValueQuantification.sku_code.in_(sku_codes or [""]))
            .order_by(
                entities.Core3SkuClaimValueQuantification.sku_code,
                desc(entities.Core3SkuClaimValueQuantification.estimated_price_premium_abs),
                desc(entities.Core3SkuClaimValueQuantification.estimated_weekly_sales_lift_abs),
            )
        ).scalars()
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            if len(grouped[row.sku_code]) < 3 and row.claim_name not in grouped[row.sku_code]:
                role_cn = CLAIM_ROLE_CN.get(row.claim_value_role, row.claim_value_role)
                grouped[row.sku_code].append(f"{row.claim_name}（{role_cn}）")
        return {sku: "；".join(values) for sku, values in grouped.items()}

    def _market_sales_by_sku(self, *, batch_id: str, sku_codes: Iterable[str]) -> dict[str, float]:
        rows = self.db.execute(
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .where(entities.Core3SkuMarketProfile.sku_code.in_(list(sku_codes) or [""]))
        ).scalars()
        result: dict[str, float] = {}
        for row in rows:
            weeks = max(int(row.active_week_count or 0), 1)
            result[row.sku_code] = _round(_number(row.sales_volume_total) / weeks if row.sales_volume_total is not None else None, 0) or 0
        return result

    def _report_urls(self, *, batch_id: str, export_type_keywords: tuple[str, ...]) -> dict[str, str]:
        rows = self.db.execute(
            select(entities.Core3ReportExport)
            .where(entities.Core3ReportExport.project_id == self.project_id)
            .where(entities.Core3ReportExport.category_code == self.category_code)
            .where(entities.Core3ReportExport.batch_id == batch_id)
            .where(entities.Core3ReportExport.is_current.is_(True))
        ).scalars()
        urls: dict[str, str] = {}
        for row in rows:
            haystack = f"{row.export_type} {row.export_title_cn}".lower()
            if not any(keyword.lower() in haystack for keyword in export_type_keywords):
                continue
            url = _find_url(row.export_payload_json) or _find_url({"payload": row.export_payload})
            if url:
                urls[row.target_sku_code] = url
        return urls


def _task_rule_version(product_category: str) -> str:
    return CORE3_M09C_AC_RULE_VERSION if product_category.lower() == "ac" else CORE3_M09C_TV_RULE_VERSION


def _group_rule_version(product_category: str) -> str:
    return CORE3_M10C_AC_RULE_VERSION if product_category.lower() == "ac" else CORE3_M10C_TV_RULE_VERSION


def _battlefield_rule_version(product_category: str) -> str:
    return CORE3_M11C_AC_RULE_VERSION if product_category.lower() == "ac" else CORE3_M11C_TV_RULE_VERSION


def _limit(stmt: Any, limit: int | None) -> Any:
    return stmt.limit(limit) if limit else stmt


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return _round(number, 2)


def _round(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _data_window(batch: entities.Core3SourceBatch | None) -> str | None:
    if not batch:
        return None
    if batch.write_time_range_json:
        values = []
        for item in batch.write_time_range_json.values():
            if isinstance(item, dict):
                start = item.get("min") or item.get("start")
                end = item.get("max") or item.get("end")
                if start or end:
                    values.append(f"{start or '?'}-{end or '?'}")
        if values:
            return "；".join(values[:3])
    start = batch.scan_started_at.strftime("%Y-%m-%d") if batch.scan_started_at else ""
    end = batch.scan_finished_at.strftime("%Y-%m-%d") if batch.scan_finished_at else ""
    return f"{start}-{end}".strip("-") or None


def _batch_note(batch: entities.Core3SourceBatch | None) -> str | None:
    if not batch:
        return "未找到源批次记录，仅发布已持久化分析结果。"
    if batch.error_message:
        return batch.error_message
    return f"源状态：{batch.status}；影响SKU：{batch.impacted_sku_count}"


def _distribution_keys(payload: Any, key_name: str) -> str | None:
    keys: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key_name in {"size_tier", "size"} and isinstance(key, str) and "_" in key:
                keys.add(key.split("|")[0])
            if isinstance(value, dict):
                candidate = value.get(key_name) or value.get(key_name.replace("_", ""))
                if candidate:
                    keys.add(str(candidate))
                for nested_key in value:
                    if key_name == "price_band" and isinstance(nested_key, str):
                        keys.add(nested_key)
    return "、".join(sorted(keys)) if keys else None


def _top_distribution(payload: Any, *, label_keys: tuple[str, ...], limit: int = 5) -> str | None:
    items: list[tuple[str, float]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                label = next((str(value.get(k)) for k in label_keys if value.get(k)), str(key))
                amount = _number(value.get("estimated_avg_weekly_sales_amount") or value.get("sales_amount") or value.get("value")) or 0
            else:
                label = str(key)
                amount = _number(value) or 0
            items.append((label, amount))
    items.sort(key=lambda item: item[1], reverse=True)
    return "、".join(label for label, _ in items[:limit]) if items else None


def _top_skus(payload: Any, limit: int = 5) -> str | None:
    if not isinstance(payload, list):
        return None
    labels: list[str] = []
    for item in payload[:limit]:
        if isinstance(item, dict):
            model = item.get("model_name") or item.get("sku_code") or item.get("name")
            brand = item.get("brand_name") or item.get("brand")
            labels.append(f"{brand or ''}{model or ''}".strip())
        else:
            labels.append(str(item))
    return "、".join(label for label in labels if label) or None


def _score(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, dict):
            value = value.get("score") or value.get("value")
        number = _number(value)
        if number is not None:
            return round(number, 4)
    return None


def _competitor_role_cn(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {
        "首选竞品": "首选直接竞品",
        "核心竞品": "强直接竞品",
        "价格贴身": "价格贴身竞品",
        "下探": "下探分流竞品",
        "上探": "上探替代竞品",
    }
    for token, label in mapping.items():
        if token in value:
            return label
    return value


def _claim_context(row: entities.Core3SkuClaimValueQuantification) -> str | None:
    if row.context_type == "battlefield":
        return row.context_name or row.context_code
    supporting = row.supporting_dimensions_json or {}
    contexts = []
    for key in ("battlefields", "battlefield", "contexts"):
        value = supporting.get(key)
        if isinstance(value, list):
            contexts.extend(str(item.get("name") or item.get("code") or item) if isinstance(item, dict) else str(item) for item in value)
        elif isinstance(value, str):
            contexts.append(value)
    return "、".join(contexts[:5]) or _market_context(row)


def _market_context(row: entities.Core3SkuClaimValueQuantification) -> str:
    return f"{row.context_name or row.context_code}；{row.size_tier}/{row.price_band_group}"


def _support_text(label: str, value: Any) -> str:
    number = _number(value) or 0
    if number >= 0.75:
        level = "强"
    elif number >= 0.45:
        level = "中"
    elif number > 0:
        level = "弱"
    else:
        level = "不足"
    return f"{label}证据{level}（{round(number, 2)}）"


def _claim_action(role_cn: str) -> str:
    mapping = {
        "高溢价卖点": "保持高端表达，优先放在价格解释和高端卖场话术中。",
        "份额转化卖点": "强化导购和页面表达，优先用于提升同池成交转化。",
        "客户获得价值卖点": "作为更值的组合理由表达，避免单独加价。",
        "人无我有型支付价值卖点": "补强用户感知和参数证明，再评估是否转入高溢价卖点。",
        "门槛卖点": "作为入围清单基础项维护，缺失会影响比较资格。",
        "待激活卖点": "补评论感知、场景表达或页面证据，推动从有基础转为可成交理由。",
        "厂家主张卖点": "谨慎作为主打，需补参数或用户评论验证。",
        "竞品拦截卖点": "跟踪竞品表达，评估是否补参数、补卖点或调整沟通重点。",
        "价格压力卖点": "检查卖点表达与实际价格是否匹配，避免削弱成交理由。",
        "样本不足待复核": "补充样本或等待更多销售周期后复核。",
    }
    return mapping.get(role_cn, "保留业务复核。")


def _confidence_label(value: Any) -> str:
    number = _number(value) or 0
    if number >= 0.75:
        return "高"
    if number >= 0.5:
        return "中"
    if number > 0:
        return "低"
    return "待复核"


def _find_url(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("url", "report_url", "document_url", "doc_url", "feishu_url", "feishu_doc_url"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        for value in payload.values():
            found = _find_url(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_url(item)
            if found:
                return found
    elif isinstance(payload, str) and payload.startswith("http"):
        return payload
    return None
