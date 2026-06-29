"""Base table schema for the XiaoAo home-appliance market workbench."""

from __future__ import annotations

from app.services.core3_real_data.publish.schemas import BaseFieldDefinition as F
from app.services.core3_real_data.publish.schemas import BaseTableDefinition, BaseViewDefinition


ANALYSIS_BATCH = "analysis-batch"
SKU_OVERVIEW = "sku-overview"
BATTLEFIELD_MAP = "battlefield-map"
COMPETITOR_RELATIONS = "competitor-relations"
CLAIM_VALUE = "claim-value"

SYNC_SCOPES = (ANALYSIS_BATCH, SKU_OVERVIEW, BATTLEFIELD_MAP, COMPETITOR_RELATIONS, CLAIM_VALUE)

CATEGORY_OPTIONS = ("TV", "AC")
SYNC_STATUS_OPTIONS = ("未同步", "同步中", "成功", "失败")
CLAIM_ROLE_OPTIONS = (
    "高溢价卖点",
    "份额转化卖点",
    "客户获得价值卖点",
    "人无我有型支付价值卖点",
    "门槛卖点",
    "待激活卖点",
    "厂家主张卖点",
    "竞品拦截卖点",
    "价格压力卖点",
    "样本不足待复核",
)
CONFIDENCE_OPTIONS = ("高", "中", "低", "待复核")
COMPETITOR_ROLE_OPTIONS = (
    "首选直接竞品",
    "强直接竞品",
    "价格贴身竞品",
    "下探分流竞品",
    "上探替代竞品",
    "场景替代竞品",
    "排除候选",
)

WORKBENCH_TABLES: dict[str, BaseTableDefinition] = {
    ANALYSIS_BATCH: BaseTableDefinition(
        scope=ANALYSIS_BATCH,
        table_name="分析批次表",
        unique_key_fields=("batch_id", "category_code"),
        fields=(
            F("unique_key", "unique_key"),
            F("batch_id", "批次ID"),
            F("category_code", "品类", "select", options=CATEGORY_OPTIONS),
            F("product_category", "业务品类"),
            F("data_window", "数据窗口"),
            F("source_batch_id", "源数据批次"),
            F("sku_count", "SKU数", "number"),
            F("comment_sku_count", "有评论SKU数", "number"),
            F("sku_overview_count", "SKU总览行数", "number"),
            F("competitor_relation_count", "竞品关系行数", "number"),
            F("claim_value_count", "用户卖点价值行数", "number"),
            F("sync_status", "同步状态", "select", options=SYNC_STATUS_OPTIONS),
            F("synced_at", "同步时间", "datetime"),
            F("note_cn", "备注"),
        ),
        views=(BaseViewDefinition("批次同步状态"),),
    ),
    SKU_OVERVIEW: BaseTableDefinition(
        scope=SKU_OVERVIEW,
        table_name="SKU总览表",
        unique_key_fields=("batch_id", "category_code", "sku_code"),
        fields=(
            F("unique_key", "unique_key"),
            F("batch_id", "批次ID"),
            F("category_code", "品类", "select", options=CATEGORY_OPTIONS),
            F("sku_code", "SKU编码"),
            F("brand_name", "品牌"),
            F("model_name", "型号"),
            F("screen_size_inch", "尺寸", "number"),
            F("size_tier", "尺寸档", "select", options=("small_32_45", "medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus", "unknown")),
            F("price_band", "价格带", "select", options=("low", "mid_low", "mid", "mid_high", "high", "unknown")),
            F("weighted_price", "均价", "number"),
            F("avg_weekly_sales_volume", "周均销量", "number"),
            F("avg_weekly_sales_amount", "周均销售额", "number"),
            F("primary_battlefield", "主价值战场"),
            F("primary_user_task", "主用户任务"),
            F("primary_target_group", "主目标客群"),
            F("top_claims_cn", "重点卖点摘要"),
            F("competitor_report_url", "竞品分析报告"),
            F("claim_value_report_url", "用户卖点价值报告"),
            F("updated_at", "更新时间", "datetime"),
        ),
        views=(
            BaseViewDefinition("SKU总览-按品牌"),
            BaseViewDefinition("SKU总览-按尺寸价格带"),
            BaseViewDefinition("海信SKU"),
        ),
    ),
    BATTLEFIELD_MAP: BaseTableDefinition(
        scope=BATTLEFIELD_MAP,
        table_name="价值战场图谱表",
        unique_key_fields=("batch_id", "category_code", "battlefield_code"),
        fields=(
            F("unique_key", "unique_key"),
            F("batch_id", "批次ID"),
            F("category_code", "品类", "select", options=CATEGORY_OPTIONS),
            F("battlefield_code", "价值战场编码"),
            F("battlefield_name", "价值战场名称"),
            F("size_tiers", "覆盖尺寸档"),
            F("price_bands", "覆盖价格带"),
            F("covered_sku_count", "覆盖SKU数", "number"),
            F("allocated_sales_volume", "分配周均销量", "number"),
            F("allocated_sales_amount", "分配周均销售额", "number"),
            F("leading_brands_cn", "主要品牌"),
            F("representative_skus_cn", "代表SKU"),
            F("business_summary_cn", "业务摘要"),
            F("updated_at", "更新时间", "datetime"),
        ),
        views=(BaseViewDefinition("价值战场空间"),),
    ),
    COMPETITOR_RELATIONS: BaseTableDefinition(
        scope=COMPETITOR_RELATIONS,
        table_name="竞品关系表",
        unique_key_fields=("batch_id", "category_code", "target_sku_code", "competitor_sku_code"),
        fields=(
            F("unique_key", "unique_key"),
            F("batch_id", "批次ID"),
            F("category_code", "品类", "select", options=CATEGORY_OPTIONS),
            F("target_sku_code", "目标SKU编码"),
            F("target_brand", "目标品牌"),
            F("target_model", "目标型号"),
            F("competitor_sku_code", "竞品SKU编码"),
            F("competitor_brand", "竞品品牌"),
            F("competitor_model", "竞品型号"),
            F("rank", "排名", "number"),
            F("competitor_role_cn", "竞品角色", "select", options=COMPETITOR_ROLE_OPTIONS),
            F("same_purchase_pool_score", "同一购买池得分", "number"),
            F("battlefield_overlap_score", "价值战场重合得分", "number"),
            F("user_task_overlap_score", "用户任务重合得分", "number"),
            F("target_group_overlap_score", "目标客群重合得分", "number"),
            F("value_anchor_overlap_score", "价值锚点替代得分", "number"),
            F("replacement_pressure_cn", "替代压力"),
            F("avg_weekly_sales_volume", "竞品周均销量", "number"),
            F("report_url", "详细报告链接"),
            F("reasoning_cn", "入选原因"),
            F("updated_at", "更新时间", "datetime"),
        ),
        views=(BaseViewDefinition("高销量竞品"),),
    ),
    CLAIM_VALUE: BaseTableDefinition(
        scope=CLAIM_VALUE,
        table_name="用户卖点价值表",
        unique_key_fields=("batch_id", "category_code", "sku_code", "claim_code", "claim_role_cn"),
        fields=(
            F("unique_key", "unique_key"),
            F("batch_id", "批次ID"),
            F("category_code", "品类", "select", options=CATEGORY_OPTIONS),
            F("sku_code", "SKU编码"),
            F("brand_name", "品牌"),
            F("model_name", "型号"),
            F("claim_code", "卖点编码"),
            F("claim_name", "卖点名称"),
            F("claim_role_cn", "卖点角色", "select", options=CLAIM_ROLE_OPTIONS),
            F("explainable_price_value", "可解释金额", "number"),
            F("explainable_weekly_sales", "可解释周均销量", "number"),
            F("main_battlefields_cn", "主要成立战场"),
            F("parameter_evidence_cn", "参数证据"),
            F("comment_evidence_cn", "评论证据"),
            F("market_validation_cn", "市场验证"),
            F("action_suggestion_cn", "行动建议"),
            F("report_url", "详细报告链接"),
            F("confidence_cn", "置信度", "select", options=CONFIDENCE_OPTIONS),
            F("updated_at", "更新时间", "datetime"),
        ),
        views=(
            BaseViewDefinition("高溢价卖点"),
            BaseViewDefinition("待激活卖点"),
            BaseViewDefinition("竞品拦截卖点"),
        ),
    ),
}


def table_definition(scope: str) -> BaseTableDefinition:
    try:
        return WORKBENCH_TABLES[scope]
    except KeyError as exc:
        raise ValueError(f"unknown publish scope: {scope}") from exc

