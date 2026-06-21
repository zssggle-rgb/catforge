"""Read-only CatForge insight CLI for SKU parameter and claim facts.

This CLI is designed for agent usage. It exposes stable, deterministic query
commands over fact-profile outputs without requiring the user to know module codes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from statistics import median
from typing import Any, Iterable, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
)
from app.services.core3_real_data.m03b_param_profile_service import (
    M03BTaxonomy,
    M03BTierDefinition,
    ac_param_taxonomy_v0_1,
    tv_param_taxonomy_v0_1,
)
from app.services.core3_real_data.m04c_claim_fact_profile_service import M04CClaimTaxonomy, tv_claim_taxonomy_v0_1
from app.services.core3_real_data.m05c_comment_fact_profile_service import M05CCommentTaxonomy, tv_comment_fact_taxonomy_v0_1
from app.services.core3_real_data.m11c_value_battlefield_service import (
    M11CValueBattlefieldTaxonomy,
    tv_value_battlefield_taxonomy_v0_1,
)


DEFAULT_PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_CATEGORY_CODE = "TV"
LATEST_BATCH = "latest"
DEFAULT_SKU_LIMIT = 50

PRODUCT_CATEGORY_CONFIGS = {
    "TV": {
        "label_cn": "彩电",
        "rule_version": CORE3_M03B_RULE_VERSION,
        "sku_prefix": "TV",
        "taxonomy_factory": tv_param_taxonomy_v0_1,
        "claim_rule_version": CORE3_M04C_TV_RULE_VERSION,
        "claim_taxonomy_version": CORE3_M04C_TV_TAXONOMY_VERSION,
        "claim_taxonomy_factory": tv_claim_taxonomy_v0_1,
        "comment_rule_version": CORE3_M05C_TV_RULE_VERSION,
        "comment_taxonomy_version": CORE3_M05C_TV_TAXONOMY_VERSION,
        "comment_taxonomy_factory": tv_comment_fact_taxonomy_v0_1,
        "value_battlefield_rule_version": CORE3_M11C_TV_RULE_VERSION,
        "value_battlefield_taxonomy_version": CORE3_M11C_TV_TAXONOMY_VERSION,
        "value_battlefield_taxonomy_factory": tv_value_battlefield_taxonomy_v0_1,
    },
    "AC": {
        "label_cn": "空调",
        "rule_version": CORE3_M03B_AC_RULE_VERSION,
        "sku_prefix": "AC",
        "taxonomy_factory": ac_param_taxonomy_v0_1,
        "claim_rule_version": None,
        "claim_taxonomy_version": None,
        "claim_taxonomy_factory": None,
        "comment_rule_version": None,
        "comment_taxonomy_version": None,
        "comment_taxonomy_factory": None,
        "value_battlefield_rule_version": None,
        "value_battlefield_taxonomy_version": None,
        "value_battlefield_taxonomy_factory": None,
    },
}

DIMENSION_ALIASES = {
    "尺寸": "size",
    "尺寸段": "size",
    "size": "size",
    "显示": "display_tech",
    "显示技术": "display_tech",
    "display": "display_tech",
    "display_tech": "display_tech",
    "背光": "display_tech",
    "控光": "local_dimming",
    "分区": "local_dimming",
    "分区控光": "local_dimming",
    "local_dimming": "local_dimming",
    "画质": "picture_overall",
    "综合画质": "picture_overall",
    "picture": "picture_overall",
    "picture_overall": "picture_overall",
    "性能": "performance",
    "performance": "performance",
    "智能": "smart",
    "smart": "smart",
    "接口": "ports",
    "端口": "ports",
    "ports": "ports",
    "外观": "appearance",
    "appearance": "appearance",
    "能效": "energy",
    "energy": "energy",
    "安装": "installation",
    "安装方式": "installation",
    "installation": "installation",
    "匹数": "horsepower",
    "horsepower": "horsepower",
    "制冷量": "cooling_capacity",
    "制冷": "cooling_capacity",
    "cooling": "cooling_capacity",
    "cooling_capacity": "cooling_capacity",
    "制热": "heating",
    "heating": "heating",
    "循环风量": "airflow",
    "风量": "airflow",
    "airflow": "airflow",
    "新风": "health",
    "净化": "health",
    "健康": "health",
    "health": "health",
    "舒适": "comfort",
    "舒适风": "comfort",
    "自清洁": "comfort",
    "comfort": "comfort",
}

CLAIM_DIMENSION_ALIASES = {
    "画质": "picture_quality",
    "显示": "picture_quality",
    "图像": "picture_quality",
    "游戏": "motion_gaming",
    "运动": "motion_gaming",
    "电竞": "motion_gaming",
    "智能": "smart_interaction",
    "语音": "smart_interaction",
    "互联": "smart_interaction",
    "音质": "audio_cinema",
    "影音": "audio_cinema",
    "影院": "audio_cinema",
    "外观": "appearance_installation",
    "安装": "appearance_installation",
    "性能": "system_performance",
    "系统": "system_performance",
    "能效": "energy_value",
    "价格": "energy_value",
    "价值": "energy_value",
    "picture_quality": "picture_quality",
    "motion_gaming": "motion_gaming",
    "smart_interaction": "smart_interaction",
    "audio_cinema": "audio_cinema",
    "appearance_installation": "appearance_installation",
    "system_performance": "system_performance",
    "energy_value": "energy_value",
}

COMMENT_DIMENSION_ALIASES = {
    "画质": "picture_screen_experience",
    "屏幕": "picture_screen_experience",
    "清晰": "picture_screen_experience",
    "音质": "audio_cinema_experience",
    "影音": "audio_cinema_experience",
    "系统": "system_interaction_experience",
    "交互": "system_interaction_experience",
    "投屏": "system_interaction_experience",
    "游戏": "gaming_motion_experience",
    "高刷": "gaming_motion_experience",
    "外观": "appearance_installation_space",
    "安装": "appearance_installation_space",
    "价格": "price_value_perception",
    "性价比": "price_value_perception",
    "人群": "audience_signal",
    "客群": "audience_signal",
    "用途": "use_case_signal",
    "任务": "use_case_signal",
    "品牌力": "brand_power_signal",
    "品牌": "brand_power_signal",
    "复购": "brand_power_signal",
    "推荐": "brand_power_signal",
    "竞品": "competitor_comparison_signal",
    "对比": "competitor_comparison_signal",
    "服务": "service_fulfillment_excluded",
    "履约": "service_fulfillment_excluded",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            if args.command == "sku-param-profile":
                product_category = resolve_product_category(args.product_category, query=args.query, sku_code=args.sku_code, model_name=args.model_name)
                result = query_sku_param_profile(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=product_category,
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    include_param_values=args.include_param_values,
                    param_limit=args.param_limit,
                )
            elif args.command == "tv-param-taxonomy":
                result = query_param_taxonomy(
                    product_category="TV",
                    group=args.group,
                    search=args.search,
                    include_excluded=args.include_excluded,
                )
            elif args.command == "ac-param-taxonomy":
                result = query_param_taxonomy(
                    product_category="AC",
                    group=args.group,
                    search=args.search,
                    include_excluded=args.include_excluded,
                )
            elif args.command == "param-taxonomy":
                result = query_param_taxonomy(
                    product_category=normalize_product_category_arg(args.product_category),
                    group=args.group,
                    search=args.search,
                    include_excluded=args.include_excluded,
                )
            elif args.command == "tier-coverage":
                product_category = resolve_product_category(args.product_category, query=args.query, dimension=args.dimension_code, tier=args.tier_code)
                result = query_tier_coverage(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=product_category,
                    dimension=args.dimension_code,
                    tier=args.tier_code,
                    query=args.query,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "claim-taxonomy":
                result = query_claim_taxonomy(
                    product_category=normalize_product_category_arg(args.product_category),
                    dimension=args.dimension,
                    search=args.search,
                )
            elif args.command == "sku-claim-profile":
                product_category = resolve_product_category(args.product_category, query=args.query, sku_code=args.sku_code, model_name=args.model_name)
                result = query_sku_claim_profile(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=product_category,
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    include_claim_facts=args.include_claim_facts,
                )
            elif args.command == "claim-position-coverage":
                product_category = resolve_product_category(args.product_category, query=args.query, dimension=args.dimension_code, tier=args.position_code)
                result = query_claim_position_coverage(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=product_category,
                    dimension=args.dimension_code,
                    position=args.position_code,
                    query=args.query,
                    position_source=args.position_source,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "comment-taxonomy":
                result = query_comment_taxonomy(
                    product_category=normalize_product_category_arg(args.product_category),
                    dimension=args.dimension,
                    search=args.search,
                )
            elif args.command == "sku-comment-profile":
                product_category = resolve_product_category(args.product_category, query=args.query, sku_code=args.sku_code, model_name=args.model_name)
                result = query_sku_comment_profile(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=product_category,
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    include_comment_facts=args.include_comment_facts,
                )
            elif args.command == "comment-dimension-coverage":
                product_category = resolve_product_category(args.product_category, query=args.query, dimension=args.dimension_code, tier=args.coverage_key)
                result = query_comment_dimension_coverage(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=product_category,
                    coverage_type=args.coverage_type,
                    coverage_key=args.coverage_key,
                    dimension=args.dimension_code,
                    query=args.query,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "sku-market-profile":
                result = query_sku_market_profile(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    analysis_window=args.analysis_window,
                    include_signals=args.include_signals,
                    include_pools=args.include_pools,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "market-bucket-coverage":
                result = query_market_bucket_coverage(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    bucket_type=args.bucket_type,
                    query=args.query,
                    analysis_window=args.analysis_window,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "comparable-pools":
                result = query_comparable_pools(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    pool_type=args.pool_type,
                    analysis_window=args.analysis_window,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "value-battlefield-taxonomy":
                result = query_value_battlefield_taxonomy(
                    product_category=normalize_product_category_arg(args.product_category),
                    battlefield_code=args.battlefield_code,
                    search=args.search,
                )
            elif args.command == "sku-value-battlefield":
                result = query_sku_value_battlefield(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=resolve_product_category(args.product_category, query=args.query, sku_code=args.sku_code, model_name=args.model_name),
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    include_scores=args.include_scores,
                )
            elif args.command == "value-battlefield-skus":
                result = query_value_battlefield_skus(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(args.product_category),
                    battlefield_code=args.battlefield_code,
                    relation_status=args.relation_status,
                    query=args.query,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "value-battlefield-graph":
                result = query_value_battlefield_graph(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(args.product_category),
                )
            elif args.command == "ask":
                result = answer_natural_language(
                    db,
                    question=" ".join(args.question),
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=args.product_category,
                    output_format=args.format,
                    sku_limit=args.sku_limit,
                )
            else:
                parser.error("missing command")
                return 2
    except CatForgeInsightError as exc:
        result = {"status": "error", "error": str(exc)}
        emit_result(result, args.format)
        return 1

    emit_result(result, args.format)
    return 0 if result.get("status") not in {"error", "not_found", "ambiguous"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.catforge_insight",
        description="Query CatForge SKU parameter profiles, claim fact profiles, taxonomies, and coverage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("sku-param-profile", help="Query one SKU/model parameter fact profile.")
    add_common_args(profile)
    add_product_category_arg(profile)
    profile.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    profile.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    profile.add_argument("--model-name", help="Exact or fuzzy model name, such as 100A4F.")
    profile.add_argument("--include-param-values", action="store_true", help="Include all extracted standard parameter values.")
    profile.add_argument("--param-limit", type=int, default=120, help="Maximum parameter values to include when --include-param-values is set.")
    add_format_arg(profile)

    taxonomy = subparsers.add_parser("tv-param-taxonomy", help="Query the TV standard parameter taxonomy.")
    taxonomy.add_argument("--group", help="Filter by parameter group, such as picture, smart, performance.")
    taxonomy.add_argument("--search", help="Search parameter code/name/raw fields.")
    taxonomy.add_argument("--include-excluded", action="store_true", help="Include raw fields intentionally excluded from standard params.")
    add_format_arg(taxonomy)

    ac_taxonomy = subparsers.add_parser("ac-param-taxonomy", help="Query the AC standard parameter taxonomy.")
    ac_taxonomy.add_argument("--group", help="Filter by parameter group, such as capacity, smart, energy.")
    ac_taxonomy.add_argument("--search", help="Search parameter code/name/raw fields.")
    ac_taxonomy.add_argument("--include-excluded", action="store_true", help="Include raw fields intentionally excluded from standard params.")
    add_format_arg(ac_taxonomy)

    generic_taxonomy = subparsers.add_parser("param-taxonomy", help="Query a product category standard parameter taxonomy.")
    add_product_category_arg(generic_taxonomy, default="tv", allow_auto=False)
    generic_taxonomy.add_argument("--group", help="Filter by parameter group.")
    generic_taxonomy.add_argument("--search", help="Search parameter code/name/raw fields.")
    generic_taxonomy.add_argument("--include-excluded", action="store_true", help="Include raw fields intentionally excluded from standard params.")
    add_format_arg(generic_taxonomy)

    coverage = subparsers.add_parser("tier-coverage", help="Query SKU coverage for parameter dimension tiers.")
    add_common_args(coverage)
    add_product_category_arg(coverage)
    coverage.add_argument("--dimension-code", help="Dimension code or alias, such as display_tech, 画质, 尺寸.")
    coverage.add_argument("--tier-code", help="Tier code, tier name, or alias, such as miniled or 旗舰画质.")
    coverage.add_argument("--query", help="Natural tier query text. Matching uses dimension/tier code, Chinese names, and rule summary.")
    coverage.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include; 0 means all.")
    add_format_arg(coverage)

    claim_taxonomy = subparsers.add_parser("claim-taxonomy", help="Query a product category standard claim taxonomy.")
    add_product_category_arg(claim_taxonomy, default="tv", allow_auto=False)
    claim_taxonomy.add_argument("--dimension", help="Filter by claim dimension.")
    claim_taxonomy.add_argument("--search", help="Search claim code/name/dimension/subtype/support params.")
    add_format_arg(claim_taxonomy)

    claim_profile = subparsers.add_parser("sku-claim-profile", help="Query one SKU/model claim fact profile.")
    add_common_args(claim_profile)
    add_product_category_arg(claim_profile)
    claim_profile.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    claim_profile.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    claim_profile.add_argument("--model-name", help="Exact or fuzzy model name, such as 100A4F.")
    claim_profile.add_argument("--include-claim-facts", action="store_true", help="Include matched claim fact rows.")
    add_format_arg(claim_profile)

    claim_coverage = subparsers.add_parser("claim-position-coverage", help="Query SKU coverage for claim dimension positions.")
    add_common_args(claim_coverage)
    add_product_category_arg(claim_coverage)
    claim_coverage.add_argument("--dimension-code", help="Claim dimension code or alias, such as picture_quality or 画质.")
    claim_coverage.add_argument("--position-code", help="Claim position code or name, such as picture_flagship_miniled_composite.")
    claim_coverage.add_argument("--position-source", choices=("supported", "claimed", "all"), default="supported", help="Use parameter-supported positions by default.")
    claim_coverage.add_argument("--query", help="Natural position query text.")
    claim_coverage.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include; 0 means all.")
    add_format_arg(claim_coverage)

    comment_taxonomy = subparsers.add_parser("comment-taxonomy", help="Query a product category comment fact taxonomy.")
    add_product_category_arg(comment_taxonomy, default="tv", allow_auto=False)
    comment_taxonomy.add_argument("--dimension", help="Filter by comment dimension.")
    comment_taxonomy.add_argument("--search", help="Search dimension/subdimension code, name, linked params, or linked claims.")
    add_format_arg(comment_taxonomy)

    comment_profile = subparsers.add_parser("sku-comment-profile", help="Query one SKU/model comment fact profile.")
    add_common_args(comment_profile)
    add_product_category_arg(comment_profile)
    comment_profile.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    comment_profile.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    comment_profile.add_argument("--model-name", help="Exact or fuzzy model name, such as 100A4F.")
    comment_profile.add_argument("--include-comment-facts", action="store_true", help="Include matched comment fact atom rows.")
    add_format_arg(comment_profile)

    comment_coverage = subparsers.add_parser("comment-dimension-coverage", help="Query SKU coverage for comment fact dimensions, signals, params, or claims.")
    add_common_args(comment_coverage)
    add_product_category_arg(comment_coverage)
    comment_coverage.add_argument(
        "--coverage-type",
        choices=(
            "all",
            "dimension",
            "subdimension",
            "audience_signal",
            "use_case_signal",
            "brand_power_signal",
            "competitor_comparison_signal",
            "service_fulfillment_excluded",
            "param_support",
            "param_contradiction",
            "claim_support",
            "claim_contradiction",
        ),
        default="all",
        help="Coverage type to query.",
    )
    comment_coverage.add_argument("--dimension-code", help="Comment dimension code or alias, such as brand_power_signal or 品牌力.")
    comment_coverage.add_argument("--coverage-key", help="Coverage key, such as brand_trust, declared_refresh_rate_hz, or tv_claim_high_refresh_rate.")
    comment_coverage.add_argument("--query", help="Natural coverage query text.")
    comment_coverage.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include; 0 means all.")
    add_format_arg(comment_coverage)

    market_profile = subparsers.add_parser("sku-market-profile", help="Query one SKU/model market profile.")
    add_common_args(market_profile)
    market_profile.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    market_profile.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    market_profile.add_argument("--model-name", help="Exact or fuzzy model name, such as 85E7Q.")
    market_profile.add_argument("--analysis-window", default="full_observed_window", choices=("full_observed_window", "latest_week", "recent_4w", "recent_8w", "recent_12w"))
    market_profile.add_argument("--include-signals", action="store_true", help="Include market signal rows for the selected window.")
    market_profile.add_argument("--include-pools", action="store_true", help="Include comparable-pool summaries for the selected window.")
    market_profile.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of pool member SKU codes to include; 0 means all.")
    add_format_arg(market_profile)

    market_bucket = subparsers.add_parser("market-bucket-coverage", help="Query price-band, size, or size-price market bucket coverage.")
    add_common_args(market_bucket)
    market_bucket.add_argument("--bucket-type", choices=("all", "price", "size", "size_price"), default="all", help="Bucket type to query. Current implementation uses M07 price band and size segment until business buckets are persisted.")
    market_bucket.add_argument("--query", help="Natural bucket query text, such as high price band, 85 size, or mid_high.")
    market_bucket.add_argument("--analysis-window", default="full_observed_window", choices=("full_observed_window", "latest_week", "recent_4w", "recent_8w", "recent_12w"))
    market_bucket.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include per bucket; 0 means all.")
    add_format_arg(market_bucket)

    comparable_pools = subparsers.add_parser("comparable-pools", help="Query comparable-pool baselines for one SKU/model.")
    add_common_args(comparable_pools)
    comparable_pools.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    comparable_pools.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    comparable_pools.add_argument("--model-name", help="Exact or fuzzy model name, such as 85E7Q.")
    comparable_pools.add_argument("--pool-type", choices=("same_size", "adjacent_size", "same_price_band", "size_price_band", "platform_overlap", "market_active"), help="Optional pool type filter.")
    comparable_pools.add_argument("--analysis-window", default="full_observed_window", choices=("full_observed_window", "latest_week", "recent_4w", "recent_8w", "recent_12w"))
    comparable_pools.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of candidate SKU codes to include per pool; 0 means all.")
    add_format_arg(comparable_pools)

    value_taxonomy = subparsers.add_parser("value-battlefield-taxonomy", help="Query a product category value battlefield taxonomy.")
    add_product_category_arg(value_taxonomy, default="tv", allow_auto=False)
    value_taxonomy.add_argument("--battlefield-code", help="Filter by battlefield code.")
    value_taxonomy.add_argument("--search", help="Search code/name/tasks/groups/claims/params.")
    add_format_arg(value_taxonomy)

    value_profile = subparsers.add_parser("sku-value-battlefield", help="Query one SKU/model value battlefield profile.")
    add_common_args(value_profile)
    add_product_category_arg(value_profile)
    value_profile.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    value_profile.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    value_profile.add_argument("--model-name", help="Exact or fuzzy model name, such as 85E7Q.")
    value_profile.add_argument("--include-scores", action="store_true", help="Include all SKU x battlefield score rows.")
    add_format_arg(value_profile)

    value_skus = subparsers.add_parser("value-battlefield-skus", help="Query SKUs covered by one value battlefield.")
    add_common_args(value_skus)
    add_product_category_arg(value_skus, default="tv", allow_auto=False)
    value_skus.add_argument("--battlefield-code", help="Battlefield code, such as BF_LARGE_SCREEN_VALUE_UPGRADE.")
    value_skus.add_argument("--relation-status", choices=("all", "primary_battlefield", "secondary_battlefield", "opportunity_battlefield", "brand_claimed_battlefield", "user_observed_battlefield", "drag_factor_battlefield"), default="all")
    value_skus.add_argument("--query", help="Natural battlefield query text.")
    value_skus.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include; 0 means all.")
    add_format_arg(value_skus)

    value_graph = subparsers.add_parser("value-battlefield-graph", help="Query the latest value battlefield graph snapshot.")
    add_common_args(value_graph)
    add_product_category_arg(value_graph, default="tv", allow_auto=False)
    add_format_arg(value_graph)

    ask = subparsers.add_parser("ask", help="Route a natural-language question to the right read-only query.")
    add_common_args(ask)
    add_product_category_arg(ask)
    ask.add_argument("question", nargs="+", help="Natural-language question.")
    ask.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include for tier coverage.")
    add_format_arg(ask)
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE)
    parser.add_argument("--batch-id", default=LATEST_BATCH)


def add_product_category_arg(parser: argparse.ArgumentParser, *, default: str = "auto", allow_auto: bool = True) -> None:
    choices = ("auto", "tv", "ac") if allow_auto else ("tv", "ac")
    parser.add_argument("--product-category", choices=choices, default=default, help="Business product category. Use auto for natural-language routing.")


def add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="text")


def query_sku_param_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    include_param_values: bool = False,
    param_limit: int = 120,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    resolved_batch_id = resolve_batch_id(db, project_id, category_code, batch_id, require_profile=True, rule_version=config["rule_version"])
    profile = find_sku_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        rule_version=config["rule_version"],
        query=query,
        sku_code=sku_code,
        model_name=model_name,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的参数画像。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
        }

    dimension_tiers = list_dimension_tiers(db, profile)
    result = {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "rule_version": profile.rule_version,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
        },
        "summary": {
            "param_completeness": decimal_to_float(profile.param_completeness),
            "known_param_count": profile.known_param_count,
            "unknown_param_count": profile.unknown_param_count,
            "conflict_count": profile.conflict_count,
            "review_required_count": profile.review_required_count,
        },
        "dimension_tier_profile": extract_dimension_tier_profile(profile, dimension_tiers),
        "dimension_tiers": [
            {
                "dimension_code": row.dimension_code,
                "tier_code": row.tier_code,
                "tier_name": row.tier_name,
                "tier_rank": row.tier_rank,
                "explanation": row.explanation,
                "basis_values": row.basis_values_json or {},
                "quality_flags": row.quality_flags or [],
            }
            for row in dimension_tiers
        ],
        "core_params": {
            "picture": profile.core_picture_params_json or {},
            "gaming": profile.core_gaming_params_json or {},
            "system": profile.core_system_params_json or {},
            "eye_care": profile.core_eye_care_params_json or {},
        },
        "quality_summary": profile.quality_summary_json or {},
        "evidence_id_count": len(profile.evidence_ids or []),
        "profile_hash": profile.profile_hash,
    }
    if include_param_values:
        param_values = profile.param_values_json or {}
        result["param_values"] = dict(list(param_values.items())[: max(param_limit, 0)])
        result["param_value_total"] = len(param_values)
    return result


def query_tv_param_taxonomy(
    *,
    group: str | None = None,
    search: str | None = None,
    include_excluded: bool = False,
) -> dict[str, Any]:
    return query_param_taxonomy(product_category="TV", group=group, search=search, include_excluded=include_excluded)


def query_param_taxonomy(
    *,
    product_category: str,
    group: str | None = None,
    search: str | None = None,
    include_excluded: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy = config["taxonomy_factory"]()
    group_norm = normalize_token(group)
    search_norm = normalize_token(search)
    params = []
    group_counts: dict[str, int] = defaultdict(int)
    raw_field_mapping: dict[str, list[str]] = defaultdict(list)
    for param in taxonomy.standard_params:
        group_counts[param.param_group] += 1
        for raw_field in param.raw_fields:
            raw_field_mapping[raw_field].append(param.param_code)
        haystack = normalize_token(
            " ".join(
                [
                    param.param_code,
                    param.param_name,
                    param.param_group,
                    " ".join(param.raw_fields),
                    param.parser,
                    param.missing_policy,
                ]
            )
        )
        if group_norm and normalize_token(param.param_group) != group_norm:
            continue
        if search_norm and search_norm not in haystack:
            continue
        params.append(
            {
                "param_code": param.param_code,
                "param_name": param.param_name,
                "param_group": param.param_group,
                "data_type": param.data_type,
                "raw_fields": list(param.raw_fields),
                "parser": param.parser,
                "unit": param.unit,
                "missing_policy": param.missing_policy,
                "required_for_core": param.required_for_core,
                "profile_sections": list(param.profile_sections),
            }
        )
    result = {
        "status": "ok",
        "category_code": taxonomy.category_code,
        "product_category_label_cn": config["label_cn"],
        "taxonomy_version": taxonomy.taxonomy_version,
        "param_count": len(params),
        "total_param_count": len(taxonomy.standard_params),
        "group_counts": dict(sorted(group_counts.items())),
        "params": params,
        "raw_field_mapping": {field: codes for field, codes in sorted(raw_field_mapping.items())},
        "dimension_tiers": [
            {
                "dimension_code": tier.dimension_code,
                "tier_code": tier.tier_code,
                "tier_name": tier.tier_name,
                "tier_rank": tier.tier_rank,
                "rule_summary": tier.rule_summary,
            }
            for tier in taxonomy.dimension_tiers
        ],
    }
    if include_excluded:
        result["excluded_raw_fields"] = taxonomy.excluded_raw_fields
    return result


def query_tier_coverage(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    dimension: str | None = None,
    tier: str | None = None,
    query: str | None = None,
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    resolved_batch_id = resolve_batch_id(db, project_id, category_code, batch_id, require_profile=True, rule_version=config["rule_version"])
    taxonomy = config["taxonomy_factory"]()
    matched_dimension = resolve_dimension(dimension, query)
    matched_tiers = resolve_tiers(taxonomy.dimension_tiers, dimension=matched_dimension, tier=tier, query=query)
    stmt = (
        select(entities.Core3ParamTierCoverage)
        .where(entities.Core3ParamTierCoverage.project_id == project_id)
        .where(entities.Core3ParamTierCoverage.category_code == category_code)
        .where(entities.Core3ParamTierCoverage.batch_id == resolved_batch_id)
        .where(entities.Core3ParamTierCoverage.rule_version == config["rule_version"])
        .where(entities.Core3ParamTierCoverage.taxonomy_version == taxonomy.taxonomy_version)
        .where(entities.Core3ParamTierCoverage.is_current.is_(True))
        .order_by(
            entities.Core3ParamTierCoverage.dimension_code,
            entities.Core3ParamTierCoverage.tier_rank,
            entities.Core3ParamTierCoverage.tier_code,
        )
    )
    if matched_dimension:
        stmt = stmt.where(entities.Core3ParamTierCoverage.dimension_code == matched_dimension)
    if matched_tiers:
        tier_pairs = {(item.dimension_code, item.tier_code) for item in matched_tiers}
        stmt = stmt.where(
            or_(
                *[
                    and_(
                        entities.Core3ParamTierCoverage.dimension_code == dimension_code,
                        entities.Core3ParamTierCoverage.tier_code == tier_code,
                    )
                    for dimension_code, tier_code in tier_pairs
                ]
            )
        )
    rows = list(db.execute(stmt).scalars())
    coverages = []
    for row in rows:
        sku_codes = list(row.sku_codes or [])
        visible_skus = sku_codes if sku_limit == 0 else sku_codes[: max(sku_limit, 0)]
        coverages.append(
            {
                "dimension_code": row.dimension_code,
                "tier_code": row.tier_code,
                "tier_name": row.tier_name,
                "tier_rank": row.tier_rank,
                "rule_summary": row.rule_summary,
                "sku_count": row.sku_count,
                "sku_ratio": decimal_to_float(row.sku_ratio),
                "coverage_status": row.coverage_status,
                "sku_codes": visible_skus,
                "sku_codes_returned": len(visible_skus),
                "sku_codes_truncated": sku_limit != 0 and len(sku_codes) > len(visible_skus),
                "sample_sku_codes": row.sample_sku_codes or [],
            }
        )
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "query": query,
        "matched_dimension": matched_dimension,
        "matched_tier_count": len(matched_tiers),
        "coverage_count": len(coverages),
        "coverages": coverages,
    }


def query_claim_taxonomy(
    *,
    product_category: str,
    dimension: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy = claim_taxonomy_for_product_category(product_category)
    dimension_code = resolve_claim_dimension(dimension, search)
    search_norm = normalize_token(search)
    claims = []
    dimension_counts: dict[str, int] = defaultdict(int)
    raw_support_mapping: dict[str, list[str]] = defaultdict(list)
    for claim in taxonomy.claims:
        dimension_counts[claim.dimension_code] += 1
        for param_code in claim.support_param_codes:
            raw_support_mapping[param_code].append(claim.claim_code)
        haystack = normalize_token(
            " ".join(
                [
                    claim.claim_code,
                    claim.claim_name,
                    claim.dimension_code,
                    claim.subtype_code,
                    claim.claim_kind,
                    " ".join(claim.support_param_codes),
                    " ".join(claim.support_keywords),
                ]
            )
        )
        if dimension_code and claim.dimension_code != dimension_code:
            continue
        if search_norm and search_norm not in haystack:
            continue
        claims.append(
            {
                "claim_code": claim.claim_code,
                "claim_name": claim.claim_name,
                "dimension_code": claim.dimension_code,
                "subtype_code": claim.subtype_code,
                "claim_kind": claim.claim_kind,
                "support_param_codes": list(claim.support_param_codes),
                "support_keywords": list(claim.support_keywords),
                "support_required": claim.support_required,
                "service_separate": claim.service_separate,
            }
        )
    return {
        "status": "ok",
        "category_code": taxonomy.product_category,
        "product_category_label_cn": config["label_cn"],
        "taxonomy_version": taxonomy.taxonomy_version,
        "claim_count": len(claims),
        "total_claim_count": len(taxonomy.claims),
        "dimension_counts": dict(sorted(dimension_counts.items())),
        "claims": claims,
        "support_param_mapping": {param_code: codes for param_code, codes in sorted(raw_support_mapping.items())},
        "positions": [
            {
                "dimension_code": position.dimension_code,
                "position_code": position.position_code,
                "position_name": position.position_name,
                "position_rank": position.position_rank,
                "rule_summary": position.rule_summary,
            }
            for position in taxonomy.positions
            if not dimension_code or position.dimension_code == dimension_code
        ],
    }


def query_sku_claim_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    include_claim_facts: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    ensure_claim_taxonomy_available(product_category)
    resolved_batch_id = resolve_claim_batch_id(db, project_id, category_code, batch_id, require_profile=True, rule_version=config["claim_rule_version"])
    profile = find_sku_claim_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        rule_version=config["claim_rule_version"],
        query=query,
        sku_code=sku_code,
        model_name=model_name,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的卖点事实画像。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
        }
    facts = list_sku_claim_facts(db, profile) if include_claim_facts else []
    positions = list_sku_claim_positions(db, profile)
    result = {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "rule_version": profile.rule_version,
        "taxonomy_version": profile.taxonomy_version,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
            "brand_name": profile.brand_name,
        },
        "claim_summary": {
            "raw_claim_count": profile.raw_claim_count,
            "matched_claim_count": profile.matched_claim_count,
            "fact_claim_count": profile.fact_claim_count,
            "unsupported_claim_count": profile.unsupported_claim_count,
            "param_unknown_claim_count": profile.param_unknown_claim_count,
            "service_separate_claim_count": profile.service_separate_claim_count,
            "confidence": decimal_to_float(profile.confidence),
        },
        "claim_codes": profile.claim_codes or [],
        "fact_claim_codes": profile.fact_claim_codes or [],
        "unsupported_claim_codes": profile.unsupported_claim_codes or [],
        "service_claim_codes": profile.service_claim_codes or [],
        "dimension_profile": profile.dimension_profile_json or {},
        "dimension_position_profile": profile.dimension_position_profile_json or {},
        "positions": [
            {
                "dimension_code": row.dimension_code,
                "position_code": row.position_code,
                "position_name": row.position_name,
                "position_rank": row.position_rank,
                "position_source": row.position_source,
                "basis_claim_codes": row.basis_claim_codes or [],
                "basis_fact_claim_codes": row.basis_fact_claim_codes or [],
                "explanation": row.explanation,
                "quality_flags": row.quality_flags or [],
            }
            for row in positions
        ],
        "quality_flags": profile.quality_flags or [],
        "profile_hash": profile.profile_hash,
    }
    if include_claim_facts:
        result["claim_facts"] = [
            {
                "claim_code": row.claim_code,
                "claim_name": row.claim_name,
                "claim_dimension": row.claim_dimension,
                "claim_subtype": row.claim_subtype,
                "claim_kind": row.claim_kind,
                "clean_claim_text": row.clean_claim_text,
                "param_support_status": row.param_support_status,
                "supporting_param_codes": row.supporting_param_codes or [],
                "support_explanation": row.support_explanation,
                "fact_claim_flag": row.fact_claim_flag,
                "service_separate_flag": row.service_separate_flag,
                "quality_flags": row.quality_flags or [],
            }
            for row in facts
        ]
    return result


def query_claim_position_coverage(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    dimension: str | None = None,
    position: str | None = None,
    query: str | None = None,
    position_source: str = "supported",
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy = claim_taxonomy_for_product_category(product_category)
    resolved_batch_id = resolve_claim_batch_id(db, project_id, category_code, batch_id, require_profile=True, rule_version=config["claim_rule_version"])
    matched_dimension = resolve_claim_dimension(dimension, query)
    matched_positions = resolve_claim_positions(taxonomy, dimension=matched_dimension, position=position, query=query)
    stmt = (
        select(entities.Core3ClaimPositionCoverage)
        .where(entities.Core3ClaimPositionCoverage.project_id == project_id)
        .where(entities.Core3ClaimPositionCoverage.category_code == category_code)
        .where(entities.Core3ClaimPositionCoverage.batch_id == resolved_batch_id)
        .where(entities.Core3ClaimPositionCoverage.rule_version == config["claim_rule_version"])
        .where(entities.Core3ClaimPositionCoverage.taxonomy_version == taxonomy.taxonomy_version)
        .where(entities.Core3ClaimPositionCoverage.is_current.is_(True))
        .order_by(
            entities.Core3ClaimPositionCoverage.position_source.desc(),
            entities.Core3ClaimPositionCoverage.dimension_code,
            entities.Core3ClaimPositionCoverage.position_rank.desc(),
            entities.Core3ClaimPositionCoverage.position_code,
        )
    )
    if position_source != "all":
        stmt = stmt.where(entities.Core3ClaimPositionCoverage.position_source == position_source)
    if matched_dimension:
        stmt = stmt.where(entities.Core3ClaimPositionCoverage.dimension_code == matched_dimension)
    if matched_positions:
        pairs = {(item.dimension_code, item.position_code) for item in matched_positions}
        stmt = stmt.where(
            or_(
                *[
                    and_(
                        entities.Core3ClaimPositionCoverage.dimension_code == dimension_code,
                        entities.Core3ClaimPositionCoverage.position_code == position_code,
                    )
                    for dimension_code, position_code in pairs
                ]
            )
        )
    rows = list(db.execute(stmt).scalars())
    coverages = []
    for row in rows:
        sku_codes = list(row.sku_codes or [])
        visible_skus = sku_codes if sku_limit == 0 else sku_codes[: max(sku_limit, 0)]
        coverages.append(
            {
                "dimension_code": row.dimension_code,
                "position_code": row.position_code,
                "position_name": row.position_name,
                "position_rank": row.position_rank,
                "position_source": row.position_source,
                "rule_summary": row.rule_summary,
                "sku_count": row.sku_count,
                "sku_ratio": decimal_to_float(row.sku_ratio),
                "coverage_status": row.coverage_status,
                "basis_claim_codes": row.basis_claim_codes or [],
                "sku_codes": visible_skus,
                "sku_codes_returned": len(visible_skus),
                "sku_codes_truncated": sku_limit != 0 and len(sku_codes) > len(visible_skus),
                "sample_sku_codes": row.sample_sku_codes or [],
            }
        )
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "query": query,
        "matched_dimension": matched_dimension,
        "matched_position_count": len(matched_positions),
        "position_source": position_source,
        "coverage_count": len(coverages),
        "coverages": coverages,
    }


def query_comment_taxonomy(
    *,
    product_category: str,
    dimension: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy = comment_taxonomy_for_product_category(product_category)
    dimension_code = resolve_comment_dimension(dimension, search)
    search_norm = normalize_token(search)
    subdimensions = []
    dimension_counts: dict[str, int] = defaultdict(int)
    param_mapping: dict[str, list[str]] = defaultdict(list)
    claim_mapping: dict[str, list[str]] = defaultdict(list)
    for item in taxonomy.subdimensions:
        dimension_counts[item.dimension_code] += 1
        for param_code in item.linked_param_codes:
            param_mapping[param_code].append(item.subdimension_code)
        for claim_code in item.linked_claim_codes:
            claim_mapping[claim_code].append(item.subdimension_code)
        haystack = normalize_token(
            " ".join(
                [
                    item.subdimension_code,
                    item.subdimension_name,
                    item.dimension_code,
                    item.dimension_name,
                    item.dimension_type,
                    " ".join(item.linked_param_codes),
                    " ".join(item.linked_claim_codes),
                    " ".join(item.patterns),
                ]
            )
        )
        if dimension_code and item.dimension_code != dimension_code:
            continue
        if search_norm and search_norm not in haystack:
            continue
        subdimensions.append(
            {
                "dimension_code": item.dimension_code,
                "dimension_name": item.dimension_name,
                "dimension_type": item.dimension_type,
                "subdimension_code": item.subdimension_code,
                "subdimension_name": item.subdimension_name,
                "linked_param_codes": list(item.linked_param_codes),
                "linked_claim_codes": list(item.linked_claim_codes),
                "patterns": list(item.patterns),
                "rule_summary": item.rule_summary,
            }
        )
    return {
        "status": "ok",
        "category_code": taxonomy.product_category,
        "product_category_label_cn": config["label_cn"],
        "taxonomy_version": taxonomy.taxonomy_version,
        "dimension_count": len(taxonomy.dimensions),
        "subdimension_count": len(subdimensions),
        "total_subdimension_count": len(taxonomy.subdimensions),
        "dimension_counts": dict(sorted(dimension_counts.items())),
        "dimensions": [
            {
                "dimension_code": dimension_item.dimension_code,
                "dimension_name": dimension_item.dimension_name,
                "dimension_type": dimension_item.dimension_type,
                "rule_summary": dimension_item.rule_summary,
            }
            for dimension_item in taxonomy.dimensions
            if not dimension_code or dimension_item.dimension_code == dimension_code
        ],
        "subdimensions": subdimensions,
        "param_mapping": {code: items for code, items in sorted(param_mapping.items())},
        "claim_mapping": {code: items for code, items in sorted(claim_mapping.items())},
    }


def query_sku_comment_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    include_comment_facts: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    ensure_comment_taxonomy_available(product_category)
    resolved_batch_id = resolve_comment_batch_id(db, project_id, category_code, batch_id, require_profile=True, rule_version=config["comment_rule_version"])
    profile = find_sku_comment_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        rule_version=config["comment_rule_version"],
        query=query,
        sku_code=sku_code,
        model_name=model_name,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的评论事实画像。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
        }
    facts = list_sku_comment_facts(db, profile) if include_comment_facts else []
    result = {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "rule_version": profile.rule_version,
        "taxonomy_version": profile.taxonomy_version,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
            "brand_name": profile.brand_name,
        },
        "comment_summary": {
            "comment_sentence_count": profile.comment_sentence_count,
            "matched_sentence_count": profile.matched_sentence_count,
            "fact_atom_count": profile.fact_atom_count,
            "product_fact_sentence_count": profile.product_fact_sentence_count,
            "positive_sentence_count": profile.positive_sentence_count,
            "negative_sentence_count": profile.negative_sentence_count,
            "mixed_sentence_count": profile.mixed_sentence_count,
            "neutral_sentence_count": profile.neutral_sentence_count,
            "service_excluded_sentence_count": profile.service_excluded_sentence_count,
            "review_required_count": profile.review_required_count,
            "confidence": decimal_to_float(profile.confidence),
        },
        "dimension_summary": profile.dimension_summary_json or {},
        "signal_summary": profile.signal_summary_json or {},
        "param_comment_support": profile.param_comment_support_json or {},
        "claim_comment_support": profile.claim_comment_support_json or {},
        "polarity_summary": profile.polarity_summary_json or {},
        "supported_param_codes": profile.supported_param_codes or [],
        "contradicted_param_codes": profile.contradicted_param_codes or [],
        "unmentioned_param_codes": profile.unmentioned_param_codes or [],
        "supported_claim_codes": profile.supported_claim_codes or [],
        "contradicted_claim_codes": profile.contradicted_claim_codes or [],
        "unmentioned_claim_codes": profile.unmentioned_claim_codes or [],
        "evidence_examples": profile.evidence_examples_json or [],
        "quality_flags": profile.quality_flags or [],
        "profile_hash": profile.profile_hash,
    }
    if include_comment_facts:
        result["comment_facts"] = [comment_fact_payload(row) for row in facts]
    return result


def query_comment_dimension_coverage(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    coverage_type: str = "all",
    coverage_key: str | None = None,
    dimension: str | None = None,
    query: str | None = None,
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy = comment_taxonomy_for_product_category(product_category)
    resolved_batch_id = resolve_comment_batch_id(db, project_id, category_code, batch_id, require_profile=True, rule_version=config["comment_rule_version"])
    matched_dimension = resolve_comment_dimension(dimension, query)
    matched_type = resolve_comment_coverage_type(coverage_type, query)
    matched_key = resolve_comment_coverage_key(taxonomy, coverage_key=coverage_key, query=query, dimension=matched_dimension)
    stmt = (
        select(entities.Core3CommentFactCoverage)
        .where(entities.Core3CommentFactCoverage.project_id == project_id)
        .where(entities.Core3CommentFactCoverage.category_code == category_code)
        .where(entities.Core3CommentFactCoverage.batch_id == resolved_batch_id)
        .where(entities.Core3CommentFactCoverage.rule_version == config["comment_rule_version"])
        .where(entities.Core3CommentFactCoverage.taxonomy_version == taxonomy.taxonomy_version)
        .where(entities.Core3CommentFactCoverage.product_category == product_category)
        .where(entities.Core3CommentFactCoverage.is_current.is_(True))
        .order_by(
            entities.Core3CommentFactCoverage.coverage_type,
            entities.Core3CommentFactCoverage.dimension_code,
            entities.Core3CommentFactCoverage.coverage_key,
        )
    )
    if matched_type != "all":
        stmt = stmt.where(entities.Core3CommentFactCoverage.coverage_type == matched_type)
    if matched_dimension:
        stmt = stmt.where(entities.Core3CommentFactCoverage.dimension_code == matched_dimension)
    if matched_key:
        stmt = stmt.where(entities.Core3CommentFactCoverage.coverage_key == matched_key)
    rows = list(db.execute(stmt).scalars())
    coverages = []
    for row in rows:
        sku_codes = list(row.sku_codes or [])
        visible_skus = sku_codes if sku_limit == 0 else sku_codes[: max(sku_limit, 0)]
        coverages.append(
            {
                "coverage_type": row.coverage_type,
                "coverage_key": row.coverage_key,
                "coverage_name": row.coverage_name,
                "dimension_code": row.dimension_code,
                "subdimension_code": row.subdimension_code,
                "rule_summary": row.rule_summary,
                "fact_atom_count": row.fact_atom_count,
                "positive_sentence_count": row.positive_sentence_count,
                "negative_sentence_count": row.negative_sentence_count,
                "mixed_sentence_count": row.mixed_sentence_count,
                "neutral_sentence_count": row.neutral_sentence_count,
                "strong_evidence_count": row.strong_evidence_count,
                "supported_param_count": row.supported_param_count,
                "contradicted_param_count": row.contradicted_param_count,
                "supported_claim_count": row.supported_claim_count,
                "contradicted_claim_count": row.contradicted_claim_count,
                "sku_count": row.sku_count,
                "sku_ratio": decimal_to_float(row.sku_ratio),
                "coverage_status": row.coverage_status,
                "supported_param_codes": row.supported_param_codes or [],
                "contradicted_param_codes": row.contradicted_param_codes or [],
                "supported_claim_codes": row.supported_claim_codes or [],
                "contradicted_claim_codes": row.contradicted_claim_codes or [],
                "sku_codes": visible_skus,
                "sku_codes_returned": len(visible_skus),
                "sku_codes_truncated": sku_limit != 0 and len(sku_codes) > len(visible_skus),
                "sample_sku_codes": row.sample_sku_codes or [],
                "top_skus": row.top_skus_json or [],
                "sample_evidence": row.sample_evidence_json or [],
                "sample_status_counts": row.sample_status_counts_json or {},
                "review_flags": row.review_flags or [],
            }
        )
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "query": query,
        "coverage_type": matched_type,
        "matched_dimension": matched_dimension,
        "matched_coverage_key": matched_key,
        "coverage_count": len(coverages),
        "coverages": coverages,
    }


def query_sku_market_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    analysis_window: str = "full_observed_window",
    include_signals: bool = False,
    include_pools: bool = False,
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    resolved_batch_id = resolve_market_batch_id(db, project_id, category_code, batch_id, require_profile=True)
    profile = find_sku_market_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        rule_version=CORE3_M07_RULE_VERSION,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        analysis_window=analysis_window,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的市场画像。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
            "analysis_window": analysis_window,
        }
    signals = list_market_signals(db, profile) if include_signals else []
    pools = list_comparable_pools(db, profile) if include_pools else []
    result = {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": resolved_batch_id,
        "rule_version": profile.rule_version,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
            "brand_name": profile.brand_name,
        },
        "analysis_window": profile.analysis_window,
        "period": {
            "period_start_raw": profile.period_start_raw,
            "period_end_raw": profile.period_end_raw,
            "active_week_count": profile.active_week_count,
            "market_row_count": profile.market_row_count,
            "latest_week_gap": profile.latest_week_gap,
        },
        "market_metrics": {
            "sales_volume_total": decimal_to_float(profile.sales_volume_total),
            "sales_amount_total": decimal_to_float(profile.sales_amount_total),
            "price_wavg": decimal_to_float(profile.price_wavg),
            "price_latest": decimal_to_float(profile.price_latest),
            "price_median": decimal_to_float(profile.price_median),
            "price_min": decimal_to_float(profile.price_min),
            "price_max": decimal_to_float(profile.price_max),
            "price_per_inch": decimal_to_float(profile.price_per_inch),
            "main_channel_type": profile.main_channel_type,
            "main_platform": profile.main_platform,
            "platform_count": profile.platform_count,
            "platform_share": profile.platform_share_json or {},
        },
        "price_position": {
            "price_band_category": profile.price_band_category,
            "price_band_size": profile.price_band_size,
            "price_percentile_in_category": decimal_to_float(profile.price_percentile_in_category),
            "price_percentile_in_size": decimal_to_float(profile.price_percentile_in_size),
            "volume_percentile_in_category": decimal_to_float(profile.volume_percentile_in_category),
            "volume_percentile_in_size": decimal_to_float(profile.volume_percentile_in_size),
            "same_pool_volume_percentile": decimal_to_float(profile.same_pool_volume_percentile),
            "same_pool_sku_count": profile.same_pool_sku_count,
            "price_gap_to_category_median": decimal_to_float(profile.price_gap_to_category_median),
            "price_gap_to_size_median": decimal_to_float(profile.price_gap_to_size_median),
            "volume_gap_to_size_median": decimal_to_float(profile.volume_gap_to_size_median),
        },
        "size_position": {
            "screen_size_inch": decimal_to_float(profile.screen_size_inch),
            "size_segment": profile.size_segment,
            "screen_size_class": profile.screen_size_class,
            "market_pool_key": profile.market_pool_key,
            "size_param_confidence": decimal_to_float(profile.size_param_confidence),
        },
        "business_bucket_position": current_market_bucket_fallback(profile),
        "quality": {
            "market_confidence": decimal_to_float(profile.market_confidence),
            "confidence_level": profile.confidence_level,
            "sample_status": profile.sample_status,
            "quality_flags": profile.quality_flags or [],
            "review_required": profile.review_required,
            "review_status": profile.review_status,
        },
        "evidence_id_count": len(profile.evidence_ids or []),
        "result_hash": profile.result_hash,
    }
    if include_signals:
        result["signals"] = [market_signal_payload(row) for row in signals]
    if include_pools:
        result["comparable_pools"] = [comparable_pool_payload(row, sku_limit=sku_limit) for row in pools]
    return result


def query_market_bucket_coverage(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    bucket_type: str = "all",
    query: str | None = None,
    analysis_window: str = "full_observed_window",
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    resolved_batch_id = resolve_market_batch_id(db, project_id, category_code, batch_id, require_profile=True)
    rows = list(
        db.execute(
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == project_id)
            .where(entities.Core3SkuMarketProfile.category_code == category_code)
            .where(entities.Core3SkuMarketProfile.batch_id == resolved_batch_id)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.analysis_window == analysis_window)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .order_by(entities.Core3SkuMarketProfile.sku_code)
        ).scalars()
    )
    bucket_types = ("price", "size", "size_price") if bucket_type == "all" else (bucket_type,)
    query_norm = normalize_token(query)
    query_tokens = set(extract_match_tokens(query or ""))
    coverages: list[dict[str, Any]] = []
    for type_code in bucket_types:
        grouped: dict[str, list[entities.Core3SkuMarketProfile]] = defaultdict(list)
        labels: dict[str, str] = {}
        for row in rows:
            code, label = market_bucket_identity(row, type_code)
            if query_norm and not market_bucket_query_matches(code, label, query_norm, query_tokens):
                continue
            grouped[code].append(row)
            labels[code] = label
        for code, profiles in grouped.items():
            coverages.append(market_bucket_coverage_payload(type_code, code, labels[code], profiles, sku_limit=sku_limit))
    coverages.sort(key=lambda item: (item["bucket_type"], item["bucket_code"]))
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": resolved_batch_id,
        "analysis_window": analysis_window,
        "bucket_type": bucket_type,
        "query": query,
        "coverage_count": len(coverages),
        "bucket_source": "current_m07_profile_fallback",
        "bucket_source_note_cn": "当前 M07 尚未持久化业务绝对价格区间，CLI 先使用动态价格带和尺寸段派生覆盖；业务区间表落地后可切换到持久化结果。",
        "coverages": coverages,
    }


def query_comparable_pools(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    pool_type: str | None = None,
    analysis_window: str = "full_observed_window",
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    resolved_batch_id = resolve_market_batch_id(db, project_id, category_code, batch_id, require_profile=True)
    profile = find_sku_market_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        rule_version=CORE3_M07_RULE_VERSION,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        analysis_window=analysis_window,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的市场画像，无法查询可比池。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
            "analysis_window": analysis_window,
        }
    pools = list_comparable_pools(db, profile, pool_type=pool_type)
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": resolved_batch_id,
        "analysis_window": analysis_window,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
            "brand_name": profile.brand_name,
        },
        "pool_type": pool_type,
        "pool_count": len(pools),
        "pools": [comparable_pool_payload(row, sku_limit=sku_limit) for row in pools],
    }


def query_value_battlefield_taxonomy(
    *,
    product_category: str,
    battlefield_code: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy_factory = config.get("value_battlefield_taxonomy_factory")
    if taxonomy_factory is None:
        raise CatForgeInsightError(f"{config['label_cn']}价值战场 taxonomy 尚未发布。")
    taxonomy: M11CValueBattlefieldTaxonomy = taxonomy_factory()
    search_norm = normalize_token(search)
    battlefield_code_norm = str(battlefield_code or "").strip().upper()
    rows = []
    for battlefield in taxonomy.battlefields:
        haystack = normalize_token(
            " ".join(
                [
                    battlefield.battlefield_code,
                    battlefield.battlefield_name,
                    battlefield.definition,
                    " ".join(battlefield.allowed_size_tiers),
                    " ".join(battlefield.allowed_price_bands),
                    " ".join(battlefield.primary_task_codes),
                    " ".join(battlefield.primary_target_group_codes),
                    " ".join(battlefield.claim_codes),
                    " ".join(battlefield.param_codes),
                    " ".join(battlefield.comment_subdimension_codes),
                ]
            )
        )
        if battlefield_code_norm and battlefield.battlefield_code != battlefield_code_norm:
            continue
        if search_norm and search_norm not in haystack:
            continue
        rows.append(
            {
                "battlefield_code": battlefield.battlefield_code,
                "battlefield_name": battlefield.battlefield_name,
                "definition": battlefield.definition,
                "market_gate": {
                    "size_tiers": list(battlefield.allowed_size_tiers),
                    "price_bands": list(battlefield.allowed_price_bands),
                    "adjacent_size_tiers": list(battlefield.adjacent_size_tiers),
                    "adjacent_price_bands": list(battlefield.adjacent_price_bands),
                },
                "primary_task_codes": list(battlefield.primary_task_codes),
                "secondary_task_codes": list(battlefield.secondary_task_codes),
                "primary_target_group_codes": list(battlefield.primary_target_group_codes),
                "comment_subdimension_codes": list(battlefield.comment_subdimension_codes),
                "claim_codes": list(battlefield.claim_codes),
                "param_codes": list(battlefield.param_codes),
            }
        )
    return {
        "status": "ok",
        "product_category": taxonomy.product_category,
        "product_category_label_cn": taxonomy.product_category_label_cn,
        "taxonomy_version": taxonomy.taxonomy_version,
        "battlefield_count": len(rows),
        "total_battlefield_count": len(taxonomy.battlefields),
        "battlefields": rows,
    }


def query_sku_value_battlefield(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    include_scores: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    resolved_batch_id = resolve_value_battlefield_batch_id(
        db,
        project_id,
        category_code,
        batch_id,
        require_profile=True,
        rule_version=config["value_battlefield_rule_version"],
    )
    profile = find_sku_value_battlefield_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        rule_version=config["value_battlefield_rule_version"],
        query=query,
        sku_code=sku_code,
        model_name=model_name,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的价值战场画像。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
        }
    scores = list_sku_value_battlefield_scores(db, profile) if include_scores else []
    result = {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "rule_version": profile.rule_version,
        "taxonomy_version": profile.taxonomy_version,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
            "brand_name": profile.brand_name,
        },
        "market_position": {
            "size_tier": profile.size_tier,
            "price_band_in_size_tier": profile.price_band_in_size_tier,
            "price_percentile_in_size_tier": decimal_to_float(profile.price_percentile_in_size_tier),
        },
        "primary_battlefield_code": profile.primary_battlefield_code,
        "primary_relation_status": profile.primary_relation_status,
        "secondary_battlefield_codes": profile.secondary_battlefield_codes_json or [],
        "opportunity_battlefield_codes": profile.opportunity_battlefield_codes_json or [],
        "drag_factor_battlefield_codes": profile.drag_factor_battlefield_codes_json or [],
        "battlefield_summary": profile.battlefield_summary_json or {},
        "quality": {
            "review_required": profile.review_required,
            "review_status": profile.review_status,
            "review_reason": profile.review_reason_json or {},
            "confidence": decimal_to_float(profile.confidence),
        },
        "evidence_id_count": len(profile.evidence_ids_json or []),
        "profile_hash": profile.profile_hash,
    }
    if include_scores:
        result["scores"] = [value_battlefield_score_payload(row) for row in scores]
    return result


def query_value_battlefield_skus(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
    battlefield_code: str | None = None,
    relation_status: str = "all",
    query: str | None = None,
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    taxonomy_factory = config.get("value_battlefield_taxonomy_factory")
    if taxonomy_factory is None:
        raise CatForgeInsightError(f"{config['label_cn']}价值战场 taxonomy 尚未发布。")
    taxonomy: M11CValueBattlefieldTaxonomy = taxonomy_factory()
    resolved_code = resolve_value_battlefield_code(taxonomy, battlefield_code=battlefield_code, query=query)
    resolved_batch_id = resolve_value_battlefield_batch_id(
        db,
        project_id,
        category_code,
        batch_id,
        require_profile=True,
        rule_version=config["value_battlefield_rule_version"],
    )
    stmt = (
        select(entities.Core3SkuValueBattlefieldScore)
        .where(entities.Core3SkuValueBattlefieldScore.project_id == project_id)
        .where(entities.Core3SkuValueBattlefieldScore.category_code == category_code)
        .where(entities.Core3SkuValueBattlefieldScore.batch_id == resolved_batch_id)
        .where(entities.Core3SkuValueBattlefieldScore.rule_version == config["value_battlefield_rule_version"])
        .where(entities.Core3SkuValueBattlefieldScore.taxonomy_version == taxonomy.taxonomy_version)
        .where(entities.Core3SkuValueBattlefieldScore.is_current.is_(True))
        .where(entities.Core3SkuValueBattlefieldScore.battlefield_code == resolved_code)
        .where(entities.Core3SkuValueBattlefieldScore.relation_status != "excluded")
        .order_by(
            entities.Core3SkuValueBattlefieldScore.battlefield_score.desc(),
            entities.Core3SkuValueBattlefieldScore.sku_code,
        )
    )
    if relation_status != "all":
        stmt = stmt.where(entities.Core3SkuValueBattlefieldScore.relation_status == relation_status)
    rows = list(db.execute(stmt).scalars())
    visible = rows if sku_limit == 0 else rows[: max(sku_limit, 0)]
    status_counts = Counter(row.relation_status for row in rows)
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "taxonomy_version": taxonomy.taxonomy_version,
        "rule_version": config["value_battlefield_rule_version"],
        "battlefield_code": resolved_code,
        "battlefield_name": taxonomy.battlefields_by_code[resolved_code].battlefield_name,
        "relation_status": relation_status,
        "sku_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "sku_codes": [row.sku_code for row in visible],
        "sku_codes_returned": len(visible),
        "sku_codes_truncated": sku_limit != 0 and len(rows) > len(visible),
        "skus": [value_battlefield_score_payload(row) for row in visible],
    }


def query_value_battlefield_graph(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str = "TV",
) -> dict[str, Any]:
    config = product_category_config(product_category)
    resolved_batch_id = resolve_value_battlefield_batch_id(
        db,
        project_id,
        category_code,
        batch_id,
        require_profile=True,
        rule_version=config["value_battlefield_rule_version"],
    )
    row = db.execute(
        select(entities.Core3ValueBattlefieldGraphSnapshot)
        .where(entities.Core3ValueBattlefieldGraphSnapshot.project_id == project_id)
        .where(entities.Core3ValueBattlefieldGraphSnapshot.category_code == category_code)
        .where(entities.Core3ValueBattlefieldGraphSnapshot.batch_id == resolved_batch_id)
        .where(entities.Core3ValueBattlefieldGraphSnapshot.rule_version == config["value_battlefield_rule_version"])
        .where(entities.Core3ValueBattlefieldGraphSnapshot.is_current.is_(True))
        .order_by(entities.Core3ValueBattlefieldGraphSnapshot.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到价值战场图谱，请先执行 run-value-battlefield。",
            "batch_id": resolved_batch_id,
        }
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "taxonomy_version": row.taxonomy_version,
        "rule_version": row.rule_version,
        "node_count": row.node_count,
        "edge_count": row.edge_count,
        "battlefield_count": row.battlefield_count,
        "sku_count": row.sku_count,
        "coverage_summary": row.coverage_summary_json or {},
        "graph": row.graph_json or {},
        "graph_hash": row.graph_hash,
    }


def answer_natural_language(
    db: Session,
    *,
    question: str,
    project_id: str,
    category_code: str,
    batch_id: str,
    product_category: str,
    output_format: str,
    sku_limit: int,
) -> dict[str, Any]:
    normalized = normalize_token(question)
    resolved_product_category = resolve_product_category(product_category, query=question)
    if should_route_to_value_battlefield_query(question, normalized):
        if any(word in question for word in ("标准战场", "战场预设", "价值战场预设", "战场 taxonomy", "战场体系", "战场分类")):
            result = query_value_battlefield_taxonomy(
                product_category=resolved_product_category,
                battlefield_code=None,
                search=None,
            )
            result["routed_command"] = "value-battlefield-taxonomy"
            return result
        if "图谱" in question:
            result = query_value_battlefield_graph(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                product_category=resolved_product_category,
            )
            result["routed_command"] = "value-battlefield-graph"
            return result
        if should_route_to_value_battlefield_coverage(question, normalized):
            result = query_value_battlefield_skus(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                product_category=resolved_product_category,
                battlefield_code=None,
                relation_status=value_battlefield_relation_from_question(question),
                query=question,
                sku_limit=sku_limit,
            )
            result["routed_command"] = "value-battlefield-skus"
            return result
        result = query_sku_value_battlefield(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            query=extract_sku_or_model_query(question) or question,
            include_scores=output_format == "json",
        )
        result["routed_command"] = "sku-value-battlefield"
        result["question"] = question
        return result
    if should_route_to_comment_query(question, normalized):
        if any(word in question for word in ("评论维度", "评论事实维度", "标准评论", "评论体系", "评论分类")):
            result = query_comment_taxonomy(
                product_category=resolved_product_category,
                dimension=question,
                search=None,
            )
            result["routed_command"] = "comment-taxonomy"
            return result
        if should_route_to_comment_coverage(question, normalized):
            result = query_comment_dimension_coverage(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                product_category=resolved_product_category,
                coverage_type="all",
                coverage_key=None,
                dimension=None,
                query=question,
                sku_limit=sku_limit,
            )
            result["routed_command"] = "comment-dimension-coverage"
            return result
        query = extract_sku_or_model_query(question)
        result = query_sku_comment_profile(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            query=query or question,
            include_comment_facts=output_format == "json",
        )
        result["routed_command"] = "sku-comment-profile"
        result["question"] = question
        return result
    if should_route_to_market_query(question, normalized):
        if should_route_to_market_bucket_coverage(question, normalized):
            result = query_market_bucket_coverage(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                bucket_type=market_bucket_type_from_question(question, normalized),
                query=question,
                sku_limit=sku_limit,
            )
            result["routed_command"] = "market-bucket-coverage"
            return result
        if should_route_to_comparable_pools(question, normalized):
            result = query_comparable_pools(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                query=extract_sku_or_model_query(question) or question,
                sku_limit=sku_limit,
            )
            result["routed_command"] = "comparable-pools"
            result["question"] = question
            return result
        result = query_sku_market_profile(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            query=extract_sku_or_model_query(question) or question,
            include_signals=output_format == "json",
            include_pools=output_format == "json",
            sku_limit=sku_limit,
        )
        result["routed_command"] = "sku-market-profile"
        result["question"] = question
        return result
    if "卖点" in question or "claim" in normalized:
        if any(word in question for word in ("标准卖点", "卖点分类", "卖点维度", "卖点体系")):
            result = query_claim_taxonomy(
                product_category=resolved_product_category,
                dimension=None,
                search=extract_claim_taxonomy_search(question),
            )
            result["routed_command"] = "claim-taxonomy"
            return result
        if should_route_to_claim_position_coverage(question, normalized):
            result = query_claim_position_coverage(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                product_category=resolved_product_category,
                dimension=None,
                position=None,
                query=question,
                position_source="supported",
                sku_limit=sku_limit,
            )
            result["routed_command"] = "claim-position-coverage"
            return result
        query = extract_sku_or_model_query(question)
        result = query_sku_claim_profile(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            query=query or question,
            include_claim_facts=output_format == "json",
        )
        result["routed_command"] = "sku-claim-profile"
        result["question"] = question
        return result
    if "标准参数" in question or "参数表" in question or "参数分类" in question:
        result = query_param_taxonomy(
            product_category=resolved_product_category,
            search=extract_taxonomy_search(question, product_category=resolved_product_category),
            include_excluded="排除" in question,
        )
        result["routed_command"] = "param-taxonomy"
        return result
    if should_route_to_tier_coverage(question, normalized):
        result = query_tier_coverage(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            dimension=None,
            tier=None,
            query=question,
            sku_limit=sku_limit,
        )
        result["routed_command"] = "tier-coverage"
        return result

    query = extract_sku_or_model_query(question)
    result = query_sku_param_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=resolved_product_category,
        query=query or question,
        include_param_values=output_format == "json",
    )
    result["routed_command"] = "sku-param-profile"
    result["question"] = question
    return result


def resolve_batch_id(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
    *,
    require_profile: bool,
    rule_version: str,
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    if require_profile:
        profile_batch_id = db.execute(
            select(entities.Core3SkuParamProfile.batch_id)
            .where(entities.Core3SkuParamProfile.project_id == project_id)
            .where(entities.Core3SkuParamProfile.category_code == category_code)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .order_by(entities.Core3SkuParamProfile.created_at.desc(), entities.Core3SkuParamProfile.batch_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile_batch_id:
            return str(profile_batch_id)
    source_batch_id = db.execute(
        select(entities.Core3SourceBatch.batch_id)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.category_code == category_code)
        .order_by(entities.Core3SourceBatch.created_at.desc(), entities.Core3SourceBatch.batch_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if source_batch_id:
        return str(source_batch_id)
    raise CatForgeInsightError(f"没有找到项目 {project_id} / {category_code} 的可用批次。")


def resolve_claim_batch_id(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
    *,
    require_profile: bool,
    rule_version: str,
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    if require_profile:
        profile_batch_id = db.execute(
            select(entities.Core3SkuClaimFactProfile.batch_id)
            .where(entities.Core3SkuClaimFactProfile.project_id == project_id)
            .where(entities.Core3SkuClaimFactProfile.category_code == category_code)
            .where(entities.Core3SkuClaimFactProfile.rule_version == rule_version)
            .where(entities.Core3SkuClaimFactProfile.is_current.is_(True))
            .order_by(entities.Core3SkuClaimFactProfile.created_at.desc(), entities.Core3SkuClaimFactProfile.batch_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile_batch_id:
            return str(profile_batch_id)
    return resolve_batch_id(db, project_id, category_code, batch_id, require_profile=False, rule_version=rule_version)


def resolve_comment_batch_id(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
    *,
    require_profile: bool,
    rule_version: str,
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    if require_profile:
        profile_batch_id = db.execute(
            select(entities.Core3SkuCommentFactProfile.batch_id)
            .where(entities.Core3SkuCommentFactProfile.project_id == project_id)
            .where(entities.Core3SkuCommentFactProfile.category_code == category_code)
            .where(entities.Core3SkuCommentFactProfile.rule_version == rule_version)
            .where(entities.Core3SkuCommentFactProfile.is_current.is_(True))
            .order_by(entities.Core3SkuCommentFactProfile.created_at.desc(), entities.Core3SkuCommentFactProfile.batch_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile_batch_id:
            return str(profile_batch_id)
    return resolve_batch_id(db, project_id, category_code, batch_id, require_profile=False, rule_version=rule_version)


def resolve_market_batch_id(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
    *,
    require_profile: bool,
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    if require_profile:
        profile_batch_id = db.execute(
            select(entities.Core3SkuMarketProfile.batch_id)
            .where(entities.Core3SkuMarketProfile.project_id == project_id)
            .where(entities.Core3SkuMarketProfile.category_code == category_code)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .order_by(entities.Core3SkuMarketProfile.created_at.desc(), entities.Core3SkuMarketProfile.batch_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile_batch_id:
            return str(profile_batch_id)
    return resolve_batch_id(db, project_id, category_code, batch_id, require_profile=False, rule_version=CORE3_M07_RULE_VERSION)


def resolve_value_battlefield_batch_id(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
    *,
    require_profile: bool,
    rule_version: str,
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    if require_profile:
        profile_batch_id = db.execute(
            select(entities.Core3SkuValueBattlefieldProfile.batch_id)
            .where(entities.Core3SkuValueBattlefieldProfile.project_id == project_id)
            .where(entities.Core3SkuValueBattlefieldProfile.category_code == category_code)
            .where(entities.Core3SkuValueBattlefieldProfile.rule_version == rule_version)
            .where(entities.Core3SkuValueBattlefieldProfile.is_current.is_(True))
            .order_by(entities.Core3SkuValueBattlefieldProfile.created_at.desc(), entities.Core3SkuValueBattlefieldProfile.batch_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile_batch_id:
            return str(profile_batch_id)
    return resolve_batch_id(db, project_id, category_code, batch_id, require_profile=False, rule_version=rule_version)


def find_sku_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    rule_version: str,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
) -> entities.Core3SkuParamProfile | list[dict[str, Any]] | None:
    if not any([query, sku_code, model_name]):
        raise CatForgeInsightError("查询 SKU 参数画像需要提供 --query、--sku-code 或 --model-name。")
    filters = [
        entities.Core3SkuParamProfile.project_id == project_id,
        entities.Core3SkuParamProfile.category_code == category_code,
        entities.Core3SkuParamProfile.batch_id == batch_id,
        entities.Core3SkuParamProfile.rule_version == rule_version,
    ]
    if sku_code:
        filters.append(func.lower(entities.Core3SkuParamProfile.sku_code) == sku_code.lower())
    elif model_name:
        model_norm = model_name.strip().lower()
        filters.append(func.lower(entities.Core3SkuParamProfile.model_name).like(f"%{escape_like(model_norm)}%", escape="\\"))
    else:
        query_norm = str(query or "").strip().lower()
        filters.append(
            or_(
                func.lower(entities.Core3SkuParamProfile.sku_code) == query_norm,
                func.lower(entities.Core3SkuParamProfile.model_name) == query_norm,
                func.lower(entities.Core3SkuParamProfile.model_name).like(f"%{escape_like(query_norm)}%", escape="\\"),
            )
        )
    rows = list(
        db.execute(
            select(entities.Core3SkuParamProfile)
            .where(*filters)
            .order_by(entities.Core3SkuParamProfile.sku_code)
            .limit(11)
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    exact_query = (sku_code or model_name or query or "").strip().lower()
    exact = [row for row in rows if row.sku_code.lower() == exact_query or (row.model_name or "").lower() == exact_query]
    if len(exact) == 1:
        return exact[0]
    return [{"sku_code": row.sku_code, "model_name": row.model_name} for row in rows[:10]]


def find_sku_claim_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    rule_version: str,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
) -> entities.Core3SkuClaimFactProfile | list[dict[str, Any]] | None:
    if not any([query, sku_code, model_name]):
        raise CatForgeInsightError("查询 SKU 卖点事实画像需要提供 --query、--sku-code 或 --model-name。")
    filters = [
        entities.Core3SkuClaimFactProfile.project_id == project_id,
        entities.Core3SkuClaimFactProfile.category_code == category_code,
        entities.Core3SkuClaimFactProfile.batch_id == batch_id,
        entities.Core3SkuClaimFactProfile.rule_version == rule_version,
        entities.Core3SkuClaimFactProfile.is_current.is_(True),
    ]
    if sku_code:
        filters.append(func.lower(entities.Core3SkuClaimFactProfile.sku_code) == sku_code.lower())
    elif model_name:
        model_norm = model_name.strip().lower()
        filters.append(func.lower(entities.Core3SkuClaimFactProfile.model_name).like(f"%{escape_like(model_norm)}%", escape="\\"))
    else:
        query_norm = str(query or "").strip().lower()
        filters.append(
            or_(
                func.lower(entities.Core3SkuClaimFactProfile.sku_code) == query_norm,
                func.lower(entities.Core3SkuClaimFactProfile.model_name) == query_norm,
                func.lower(entities.Core3SkuClaimFactProfile.model_name).like(f"%{escape_like(query_norm)}%", escape="\\"),
            )
        )
    rows = list(
        db.execute(
            select(entities.Core3SkuClaimFactProfile)
            .where(*filters)
            .order_by(entities.Core3SkuClaimFactProfile.sku_code)
            .limit(11)
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    exact_query = (sku_code or model_name or query or "").strip().lower()
    exact = [row for row in rows if row.sku_code.lower() == exact_query or (row.model_name or "").lower() == exact_query]
    if len(exact) == 1:
        return exact[0]
    return [{"sku_code": row.sku_code, "model_name": row.model_name, "brand_name": row.brand_name} for row in rows[:10]]


def find_sku_comment_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    rule_version: str,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
) -> entities.Core3SkuCommentFactProfile | list[dict[str, Any]] | None:
    if not any([query, sku_code, model_name]):
        raise CatForgeInsightError("查询 SKU 评论事实画像需要提供 --query、--sku-code 或 --model-name。")
    filters = [
        entities.Core3SkuCommentFactProfile.project_id == project_id,
        entities.Core3SkuCommentFactProfile.category_code == category_code,
        entities.Core3SkuCommentFactProfile.batch_id == batch_id,
        entities.Core3SkuCommentFactProfile.rule_version == rule_version,
        entities.Core3SkuCommentFactProfile.is_current.is_(True),
    ]
    if sku_code:
        filters.append(func.lower(entities.Core3SkuCommentFactProfile.sku_code) == sku_code.lower())
    elif model_name:
        model_norm = model_name.strip().lower()
        filters.append(func.lower(entities.Core3SkuCommentFactProfile.model_name).like(f"%{escape_like(model_norm)}%", escape="\\"))
    else:
        query_norm = str(query or "").strip().lower()
        filters.append(
            or_(
                func.lower(entities.Core3SkuCommentFactProfile.sku_code) == query_norm,
                func.lower(entities.Core3SkuCommentFactProfile.model_name) == query_norm,
                func.lower(entities.Core3SkuCommentFactProfile.model_name).like(f"%{escape_like(query_norm)}%", escape="\\"),
            )
        )
    rows = list(
        db.execute(
            select(entities.Core3SkuCommentFactProfile)
            .where(*filters)
            .order_by(entities.Core3SkuCommentFactProfile.sku_code)
            .limit(11)
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    exact_query = (sku_code or model_name or query or "").strip().lower()
    exact = [row for row in rows if row.sku_code.lower() == exact_query or (row.model_name or "").lower() == exact_query]
    if len(exact) == 1:
        return exact[0]
    return [{"sku_code": row.sku_code, "model_name": row.model_name, "brand_name": row.brand_name} for row in rows[:10]]


def find_sku_value_battlefield_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    rule_version: str,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
) -> entities.Core3SkuValueBattlefieldProfile | list[dict[str, Any]] | None:
    if not any([query, sku_code, model_name]):
        raise CatForgeInsightError("查询 SKU 价值战场画像需要提供 --query、--sku-code 或 --model-name。")
    filters = [
        entities.Core3SkuValueBattlefieldProfile.project_id == project_id,
        entities.Core3SkuValueBattlefieldProfile.category_code == category_code,
        entities.Core3SkuValueBattlefieldProfile.batch_id == batch_id,
        entities.Core3SkuValueBattlefieldProfile.rule_version == rule_version,
        entities.Core3SkuValueBattlefieldProfile.is_current.is_(True),
    ]
    if sku_code:
        filters.append(func.lower(entities.Core3SkuValueBattlefieldProfile.sku_code) == sku_code.lower())
    elif model_name:
        model_norm = model_name.strip().lower()
        filters.append(func.lower(entities.Core3SkuValueBattlefieldProfile.model_name).like(f"%{escape_like(model_norm)}%", escape="\\"))
    else:
        query_norm = str(query or "").strip().lower()
        filters.append(
            or_(
                func.lower(entities.Core3SkuValueBattlefieldProfile.sku_code) == query_norm,
                func.lower(entities.Core3SkuValueBattlefieldProfile.model_name) == query_norm,
                func.lower(entities.Core3SkuValueBattlefieldProfile.model_name).like(f"%{escape_like(query_norm)}%", escape="\\"),
            )
        )
    rows = list(
        db.execute(
            select(entities.Core3SkuValueBattlefieldProfile)
            .where(*filters)
            .order_by(entities.Core3SkuValueBattlefieldProfile.sku_code)
            .limit(11)
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    exact_query = (sku_code or model_name or query or "").strip().lower()
    exact = [row for row in rows if row.sku_code.lower() == exact_query or (row.model_name or "").lower() == exact_query]
    if len(exact) == 1:
        return exact[0]
    return [{"sku_code": row.sku_code, "model_name": row.model_name, "brand_name": row.brand_name} for row in rows[:10]]


def list_sku_value_battlefield_scores(
    db: Session,
    profile: entities.Core3SkuValueBattlefieldProfile,
) -> list[entities.Core3SkuValueBattlefieldScore]:
    return list(
        db.execute(
            select(entities.Core3SkuValueBattlefieldScore)
            .where(entities.Core3SkuValueBattlefieldScore.project_id == profile.project_id)
            .where(entities.Core3SkuValueBattlefieldScore.category_code == profile.category_code)
            .where(entities.Core3SkuValueBattlefieldScore.batch_id == profile.batch_id)
            .where(entities.Core3SkuValueBattlefieldScore.sku_code == profile.sku_code)
            .where(entities.Core3SkuValueBattlefieldScore.rule_version == profile.rule_version)
            .where(entities.Core3SkuValueBattlefieldScore.taxonomy_version == profile.taxonomy_version)
            .where(entities.Core3SkuValueBattlefieldScore.is_current.is_(True))
            .order_by(
                entities.Core3SkuValueBattlefieldScore.relation_status,
                entities.Core3SkuValueBattlefieldScore.battlefield_score.desc(),
            )
        ).scalars()
    )


def value_battlefield_score_payload(row: entities.Core3SkuValueBattlefieldScore) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "model_name": row.model_name,
        "brand_name": row.brand_name,
        "battlefield_code": row.battlefield_code,
        "battlefield_name": row.battlefield_name,
        "relation_status": row.relation_status,
        "value_effect": row.value_effect,
        "battlefield_score": decimal_to_float(row.battlefield_score),
        "market_gate_status": row.market_gate_status,
        "size_tier": row.size_tier,
        "price_band_in_size_tier": row.price_band_in_size_tier,
        "user_voice_score": decimal_to_float(row.user_voice_score),
        "task_group_fit_score": decimal_to_float(row.task_group_fit_score),
        "claim_alignment_score": decimal_to_float(row.claim_alignment_score),
        "param_capability_score": decimal_to_float(row.param_capability_score),
        "market_validation_score": decimal_to_float(row.market_validation_score),
        "sentiment_polarity": row.sentiment_polarity,
        "status_reason_cn": row.status_reason_cn,
        "score_breakdown": row.score_breakdown_json or {},
        "review_required": row.review_required,
        "confidence": decimal_to_float(row.confidence),
    }


def resolve_value_battlefield_code(
    taxonomy: M11CValueBattlefieldTaxonomy,
    *,
    battlefield_code: str | None,
    query: str | None,
) -> str:
    if battlefield_code:
        normalized_code = battlefield_code.strip().upper()
        if normalized_code in taxonomy.battlefields_by_code:
            return normalized_code
        raise CatForgeInsightError(f"未知价值战场 code：{battlefield_code}")
    query_norm = normalize_token(query)
    matches = [
        item
        for item in taxonomy.battlefields
        if normalize_token(item.battlefield_code) in query_norm or normalize_token(item.battlefield_name) in query_norm
    ]
    if len(matches) == 1:
        return matches[0].battlefield_code
    if len(matches) > 1:
        raise CatForgeInsightError("自然语言匹配到多个价值战场，请补充 battlefield code。")
    for item in taxonomy.battlefields:
        tokens = set(extract_match_tokens(query or ""))
        haystack = normalize_token(" ".join([item.battlefield_name, item.definition, " ".join(item.primary_task_codes), " ".join(item.primary_target_group_codes)]))
        if any(normalize_token(token) in haystack for token in tokens):
            return item.battlefield_code
    raise CatForgeInsightError("没有识别出要查询的价值战场，请提供 --battlefield-code。")


def find_sku_market_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    rule_version: str,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
    analysis_window: str,
) -> entities.Core3SkuMarketProfile | list[dict[str, Any]] | None:
    if not any([query, sku_code, model_name]):
        raise CatForgeInsightError("查询 SKU 市场画像需要提供 --query、--sku-code 或 --model-name。")
    filters = [
        entities.Core3SkuMarketProfile.project_id == project_id,
        entities.Core3SkuMarketProfile.category_code == category_code,
        entities.Core3SkuMarketProfile.batch_id == batch_id,
        entities.Core3SkuMarketProfile.rule_version == rule_version,
        entities.Core3SkuMarketProfile.analysis_window == analysis_window,
        entities.Core3SkuMarketProfile.is_current.is_(True),
    ]
    if sku_code:
        filters.append(func.lower(entities.Core3SkuMarketProfile.sku_code) == sku_code.lower())
    elif model_name:
        model_norm = model_name.strip().lower()
        filters.append(func.lower(entities.Core3SkuMarketProfile.model_name).like(f"%{escape_like(model_norm)}%", escape="\\"))
    else:
        query_norm = str(query or "").strip().lower()
        filters.append(
            or_(
                func.lower(entities.Core3SkuMarketProfile.sku_code) == query_norm,
                func.lower(entities.Core3SkuMarketProfile.model_name) == query_norm,
                func.lower(entities.Core3SkuMarketProfile.model_name).like(f"%{escape_like(query_norm)}%", escape="\\"),
            )
        )
    rows = list(
        db.execute(
            select(entities.Core3SkuMarketProfile)
            .where(*filters)
            .order_by(entities.Core3SkuMarketProfile.sku_code)
            .limit(11)
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    exact_query = (sku_code or model_name or query or "").strip().lower()
    exact = [row for row in rows if row.sku_code.lower() == exact_query or (row.model_name or "").lower() == exact_query]
    if len(exact) == 1:
        return exact[0]
    return [{"sku_code": row.sku_code, "model_name": row.model_name, "brand_name": row.brand_name} for row in rows[:10]]


def list_dimension_tiers(db: Session, profile: entities.Core3SkuParamProfile) -> list[entities.Core3SkuParamDimensionTier]:
    return list(
        db.execute(
            select(entities.Core3SkuParamDimensionTier)
            .where(entities.Core3SkuParamDimensionTier.project_id == profile.project_id)
            .where(entities.Core3SkuParamDimensionTier.category_code == profile.category_code)
            .where(entities.Core3SkuParamDimensionTier.batch_id == profile.batch_id)
            .where(entities.Core3SkuParamDimensionTier.sku_code == profile.sku_code)
            .where(entities.Core3SkuParamDimensionTier.rule_version == profile.rule_version)
            .where(entities.Core3SkuParamDimensionTier.taxonomy_version == profile.seed_version)
            .where(entities.Core3SkuParamDimensionTier.is_current.is_(True))
            .order_by(entities.Core3SkuParamDimensionTier.dimension_code)
        ).scalars()
    )


def list_sku_claim_facts(db: Session, profile: entities.Core3SkuClaimFactProfile) -> list[entities.Core3SkuClaimFact]:
    return list(
        db.execute(
            select(entities.Core3SkuClaimFact)
            .where(entities.Core3SkuClaimFact.project_id == profile.project_id)
            .where(entities.Core3SkuClaimFact.category_code == profile.category_code)
            .where(entities.Core3SkuClaimFact.batch_id == profile.batch_id)
            .where(entities.Core3SkuClaimFact.sku_code == profile.sku_code)
            .where(entities.Core3SkuClaimFact.rule_version == profile.rule_version)
            .where(entities.Core3SkuClaimFact.taxonomy_version == profile.taxonomy_version)
            .where(entities.Core3SkuClaimFact.is_current.is_(True))
            .order_by(entities.Core3SkuClaimFact.claim_dimension, entities.Core3SkuClaimFact.claim_code, entities.Core3SkuClaimFact.source_claim_key)
        ).scalars()
    )


def list_sku_claim_positions(db: Session, profile: entities.Core3SkuClaimFactProfile) -> list[entities.Core3SkuClaimDimensionPosition]:
    return list(
        db.execute(
            select(entities.Core3SkuClaimDimensionPosition)
            .where(entities.Core3SkuClaimDimensionPosition.project_id == profile.project_id)
            .where(entities.Core3SkuClaimDimensionPosition.category_code == profile.category_code)
            .where(entities.Core3SkuClaimDimensionPosition.batch_id == profile.batch_id)
            .where(entities.Core3SkuClaimDimensionPosition.sku_code == profile.sku_code)
            .where(entities.Core3SkuClaimDimensionPosition.rule_version == profile.rule_version)
            .where(entities.Core3SkuClaimDimensionPosition.taxonomy_version == profile.taxonomy_version)
            .where(entities.Core3SkuClaimDimensionPosition.is_current.is_(True))
            .order_by(entities.Core3SkuClaimDimensionPosition.position_source, entities.Core3SkuClaimDimensionPosition.dimension_code)
        ).scalars()
    )


def list_sku_comment_facts(db: Session, profile: entities.Core3SkuCommentFactProfile) -> list[entities.Core3CommentFactAtom]:
    return list(
        db.execute(
            select(entities.Core3CommentFactAtom)
            .where(entities.Core3CommentFactAtom.project_id == profile.project_id)
            .where(entities.Core3CommentFactAtom.category_code == profile.category_code)
            .where(entities.Core3CommentFactAtom.batch_id == profile.batch_id)
            .where(entities.Core3CommentFactAtom.sku_code == profile.sku_code)
            .where(entities.Core3CommentFactAtom.rule_version == profile.rule_version)
            .where(entities.Core3CommentFactAtom.taxonomy_version == profile.taxonomy_version)
            .where(entities.Core3CommentFactAtom.is_current.is_(True))
            .order_by(
                entities.Core3CommentFactAtom.dimension_code,
                entities.Core3CommentFactAtom.subdimension_code,
                entities.Core3CommentFactAtom.source_comment_key,
            )
        ).scalars()
    )


def list_market_signals(db: Session, profile: entities.Core3SkuMarketProfile) -> list[entities.Core3MarketSignal]:
    return list(
        db.execute(
            select(entities.Core3MarketSignal)
            .where(entities.Core3MarketSignal.project_id == profile.project_id)
            .where(entities.Core3MarketSignal.category_code == profile.category_code)
            .where(entities.Core3MarketSignal.batch_id == profile.batch_id)
            .where(entities.Core3MarketSignal.sku_code == profile.sku_code)
            .where(entities.Core3MarketSignal.analysis_window == profile.analysis_window)
            .where(entities.Core3MarketSignal.rule_version == profile.rule_version)
            .where(entities.Core3MarketSignal.is_current.is_(True))
            .order_by(entities.Core3MarketSignal.signal_code, entities.Core3MarketSignal.comparison_scope)
        ).scalars()
    )


def list_comparable_pools(
    db: Session,
    profile: entities.Core3SkuMarketProfile,
    *,
    pool_type: str | None = None,
) -> list[entities.Core3ComparablePoolBaseline]:
    filters = [
        entities.Core3ComparablePoolBaseline.project_id == profile.project_id,
        entities.Core3ComparablePoolBaseline.category_code == profile.category_code,
        entities.Core3ComparablePoolBaseline.batch_id == profile.batch_id,
        entities.Core3ComparablePoolBaseline.target_sku_code == profile.sku_code,
        entities.Core3ComparablePoolBaseline.analysis_window == profile.analysis_window,
        entities.Core3ComparablePoolBaseline.rule_version == profile.rule_version,
        entities.Core3ComparablePoolBaseline.is_current.is_(True),
    ]
    if pool_type:
        filters.append(entities.Core3ComparablePoolBaseline.pool_type == pool_type)
    return list(
        db.execute(
            select(entities.Core3ComparablePoolBaseline)
            .where(*filters)
            .order_by(entities.Core3ComparablePoolBaseline.pool_type)
        ).scalars()
    )


def extract_dimension_tier_profile(
    profile: entities.Core3SkuParamProfile,
    dimension_tiers: Iterable[entities.Core3SkuParamDimensionTier],
) -> dict[str, str]:
    values = profile.param_values_json or {}
    tier_profile = values.get("dimension_tier_profile")
    if isinstance(tier_profile, dict):
        return {str(key): str(value) for key, value in tier_profile.items()}
    return {row.dimension_code: row.tier_code for row in dimension_tiers}


def resolve_dimension(dimension: str | None, query: str | None) -> str | None:
    candidates = [dimension] if dimension else []
    if query:
        candidates.append(query)
    for candidate in candidates:
        candidate_norm = normalize_token(candidate)
        for alias, code in DIMENSION_ALIASES.items():
            if normalize_token(alias) in candidate_norm:
                return code
        if candidate_norm in {normalize_token(code) for code in DIMENSION_ALIASES.values()}:
            return candidate_norm
    return None


def resolve_tiers(
    tiers: Sequence[M03BTierDefinition],
    *,
    dimension: str | None,
    tier: str | None,
    query: str | None,
) -> list[M03BTierDefinition]:
    if not tier and not query:
        return []
    query_text = " ".join(value for value in (tier, query) if value)
    query_norm = normalize_token(query_text)
    query_tokens = set(extract_match_tokens(query_text))
    if not query_norm and not query_tokens:
        return []
    matches = []
    for item in tiers:
        if dimension and item.dimension_code != dimension:
            continue
        if should_skip_negative_tier_match(query_text, item):
            continue
        identity_haystack = normalize_token(" ".join([item.dimension_code, item.tier_code, item.tier_name]))
        exact_terms = {
            normalize_token(item.dimension_code),
            normalize_token(item.tier_code),
            normalize_token(item.tier_name),
        }
        if query_norm in exact_terms or any(token and token in identity_haystack for token in query_tokens):
            matches.append(item)
    if tier and not matches:
        tier_norm = normalize_token(tier)
        matches = [
            item
            for item in tiers
            if (not dimension or item.dimension_code == dimension)
            and (normalize_token(item.tier_code) == tier_norm or normalize_token(item.tier_name) == tier_norm)
        ]
    return matches


def resolve_claim_dimension(dimension: str | None, query: str | None) -> str | None:
    candidates = [dimension] if dimension else []
    if query:
        candidates.append(query)
    for candidate in candidates:
        candidate_norm = normalize_token(candidate)
        for alias, code in CLAIM_DIMENSION_ALIASES.items():
            if normalize_token(alias) in candidate_norm:
                return code
    return None


def resolve_claim_positions(
    taxonomy: M04CClaimTaxonomy,
    *,
    dimension: str | None,
    position: str | None,
    query: str | None,
) -> list[Any]:
    if not position and not query:
        return []
    query_text = " ".join(value for value in (position, query) if value)
    query_norm = normalize_token(query_text)
    query_tokens = set(extract_match_tokens(query_text))
    matches = []
    for item in taxonomy.positions:
        if dimension and item.dimension_code != dimension:
            continue
        identity_haystack = normalize_token(" ".join([item.dimension_code, item.position_code, item.position_name, item.rule_summary]))
        exact_terms = {
            normalize_token(item.dimension_code),
            normalize_token(item.position_code),
            normalize_token(item.position_name),
        }
        if query_norm in exact_terms or any(token and token in identity_haystack for token in query_tokens):
            matches.append(item)
    if position and not matches:
        position_norm = normalize_token(position)
        matches = [
            item
            for item in taxonomy.positions
            if (not dimension or item.dimension_code == dimension)
            and (normalize_token(item.position_code) == position_norm or normalize_token(item.position_name) == position_norm)
        ]
    return matches


def resolve_comment_dimension(dimension: str | None, query: str | None) -> str | None:
    candidates = [dimension] if dimension else []
    if query:
        candidates.append(query)
    for candidate in candidates:
        candidate_norm = normalize_token(candidate)
        for alias, code in COMMENT_DIMENSION_ALIASES.items():
            if normalize_token(alias) in candidate_norm:
                return code
        if candidate_norm in {normalize_token(code) for code in COMMENT_DIMENSION_ALIASES.values()}:
            return candidate_norm
    return None


def resolve_comment_coverage_type(coverage_type: str, query: str | None) -> str:
    if coverage_type and coverage_type != "all":
        return coverage_type
    query_norm = normalize_token(query)
    if not query_norm:
        return "all"
    if any(token in query_norm for token in ("品牌力", "复购", "品牌信任", "回购")):
        return "brand_power_signal"
    if any(token in query_norm for token in ("人群", "客群", "老人", "儿童", "家庭")):
        return "audience_signal"
    if any(token in query_norm for token in ("用途", "任务", "客厅", "卧室", "游戏", "投屏")):
        return "use_case_signal"
    if any(token in query_norm for token in ("竞品", "对比", "替换")):
        return "competitor_comparison_signal"
    if any(token in query_norm for token in ("参数支撑", "参数支持")):
        return "param_support"
    if any(token in query_norm for token in ("参数反证", "参数负面", "参数矛盾")):
        return "param_contradiction"
    if any(token in query_norm for token in ("卖点支撑", "卖点支持")):
        return "claim_support"
    if any(token in query_norm for token in ("卖点反证", "卖点负面", "卖点矛盾")):
        return "claim_contradiction"
    return "all"


def resolve_comment_coverage_key(
    taxonomy: M05CCommentTaxonomy,
    *,
    coverage_key: str | None,
    query: str | None,
    dimension: str | None,
) -> str | None:
    if coverage_key:
        return coverage_key
    if not query:
        return None
    query_norm = normalize_token(query)
    for item in taxonomy.subdimensions:
        if dimension and item.dimension_code != dimension:
            continue
        haystack = normalize_token(" ".join([item.subdimension_code, item.subdimension_name, item.dimension_code, item.dimension_name]))
        if normalize_token(item.subdimension_code) in query_norm or normalize_token(item.subdimension_name) in query_norm:
            return item.subdimension_code
        if any(token and token in haystack for token in extract_match_tokens(query)):
            return item.subdimension_code
    return None


def comment_fact_payload(row: entities.Core3CommentFactAtom) -> dict[str, Any]:
    return {
        "dimension_code": row.dimension_code,
        "dimension_name": row.dimension_name,
        "subdimension_code": row.subdimension_code,
        "subdimension_name": row.subdimension_name,
        "dimension_type": row.dimension_type,
        "polarity": row.polarity,
        "evidence_strength": row.evidence_strength,
        "support_relation": row.support_relation,
        "support_target_type": row.support_target_type,
        "supported_param_codes": row.supported_param_codes or [],
        "contradicted_param_codes": row.contradicted_param_codes or [],
        "supported_claim_codes": row.supported_claim_codes or [],
        "contradicted_claim_codes": row.contradicted_claim_codes or [],
        "clean_comment_text": row.clean_comment_text,
        "source_comment_key": row.source_comment_key,
        "evidence_ids": row.evidence_ids or [],
        "quality_flags": row.quality_flags or [],
        "confidence": decimal_to_float(row.confidence),
    }


def market_signal_payload(row: entities.Core3MarketSignal) -> dict[str, Any]:
    return {
        "signal_code": row.signal_code,
        "signal_name": row.signal_name,
        "signal_value": decimal_to_float(row.signal_value),
        "signal_strength": decimal_to_float(row.signal_strength),
        "signal_level": row.signal_level,
        "basis_metric": row.basis_metric,
        "basis_value": row.basis_value_json or {},
        "comparison_scope": row.comparison_scope,
        "comparison_scope_key": row.comparison_scope_key,
        "polarity": row.polarity,
        "confidence": decimal_to_float(row.confidence),
        "sample_status": row.sample_status,
        "quality_flags": row.quality_flags or [],
    }


def comparable_pool_payload(row: entities.Core3ComparablePoolBaseline, *, sku_limit: int) -> dict[str, Any]:
    sku_codes = list(row.candidate_sku_codes or [])
    visible_skus = sku_codes if sku_limit == 0 else sku_codes[: max(sku_limit, 0)]
    return {
        "pool_id": row.pool_id,
        "pool_type": row.pool_type,
        "analysis_window": row.analysis_window,
        "pool_sku_count": row.pool_sku_count,
        "valid_member_count": row.valid_member_count,
        "target_included": row.target_included,
        "target_size_segment": row.target_size_segment,
        "target_price_band": row.target_price_band,
        "median_price": decimal_to_float(row.median_price),
        "median_volume": decimal_to_float(row.median_volume),
        "median_amount": decimal_to_float(row.median_amount),
        "pool_confidence": decimal_to_float(row.pool_confidence),
        "sample_status": row.sample_status,
        "basis": row.basis,
        "candidate_sku_codes": visible_skus,
        "candidate_sku_codes_returned": len(visible_skus),
        "candidate_sku_codes_truncated": sku_limit != 0 and len(sku_codes) > len(visible_skus),
        "quality_flags": row.quality_flags or [],
    }


def current_market_bucket_fallback(profile: entities.Core3SkuMarketProfile) -> dict[str, Any]:
    price_code, price_label = market_bucket_identity(profile, "price")
    size_code, size_label = market_bucket_identity(profile, "size")
    size_price_code, size_price_label = market_bucket_identity(profile, "size_price")
    return {
        "bucket_source": "current_m07_profile_fallback",
        "price_bucket_code": price_code,
        "price_bucket_label": price_label,
        "price_bucket_basis": "price_band_category",
        "size_bucket_code": size_code,
        "size_bucket_label": size_label,
        "size_bucket_basis": "size_segment",
        "size_price_bucket_code": size_price_code,
        "size_price_bucket_label": size_price_label,
        "note_cn": "当前 M07 尚未持久化业务绝对价格区间，暂以动态价格带和尺寸段表达市场区间。",
    }


def market_bucket_identity(profile: entities.Core3SkuMarketProfile, bucket_type: str) -> tuple[str, str]:
    if bucket_type == "price":
        code = str(getattr(profile, "business_price_bucket_code", None) or profile.price_band_category or "unknown")
        label = str(getattr(profile, "business_price_bucket_label", None) or price_band_label(code))
        return code, label
    if bucket_type == "size":
        code = str(getattr(profile, "size_bucket_code", None) or profile.size_segment or profile.screen_size_class or "unknown")
        label = str(getattr(profile, "size_bucket_label", None) or size_bucket_label(code, profile.screen_size_inch))
        return code, label
    if bucket_type == "size_price":
        price_code, price_label = market_bucket_identity(profile, "price")
        size_code, size_label = market_bucket_identity(profile, "size")
        return f"{size_code}|{price_code}", f"{size_label} / {price_label}"
    raise CatForgeInsightError(f"不支持的市场区间类型：{bucket_type}")


def market_bucket_query_matches(code: str, label: str, query_norm: str, query_tokens: set[str]) -> bool:
    haystack = normalize_token(" ".join([code, label]))
    if query_norm in haystack or haystack in query_norm:
        return True
    if any(token and token in haystack for token in query_tokens):
        return True
    aliases = {
        "high": ("高", "高价", "高价格", "高价格带", "高价位"),
        "mid_high": ("中高", "中高价", "中高价格", "中高价格带", "中高价位"),
        "mid": ("中", "中价", "中价格", "中价格带", "中价位"),
        "mid_low": ("中低", "中低价", "中低价格", "中低价格带", "中低价位"),
        "low": ("低", "低价", "低价格", "低价格带", "低价位"),
    }
    return any(normalize_token(alias) in query_norm for alias in aliases.get(code, ()))


def price_band_label(code: str) -> str:
    labels = {
        "low": "低价位",
        "mid_low": "中低价位",
        "mid": "中价位",
        "mid_high": "中高价位",
        "high": "高价位",
        "unknown": "价格未知",
    }
    return labels.get(code, code)


def size_bucket_label(code: str, screen_size: Any) -> str:
    if code and code != "unknown":
        return f"{code} 寸" if str(code).replace(".", "", 1).isdigit() else str(code)
    if screen_size is not None:
        return f"{decimal_to_float(screen_size)} 寸"
    return "尺寸未知"


def market_bucket_coverage_payload(
    bucket_type: str,
    code: str,
    label: str,
    profiles: list[entities.Core3SkuMarketProfile],
    *,
    sku_limit: int,
) -> dict[str, Any]:
    sorted_profiles = sorted(
        profiles,
        key=lambda item: decimal_sort_value(item.sales_volume_total),
        reverse=True,
    )
    sku_codes = [item.sku_code for item in sorted_profiles]
    visible_skus = sku_codes if sku_limit == 0 else sku_codes[: max(sku_limit, 0)]
    volumes = [decimal_value(item.sales_volume_total) for item in profiles if item.sales_volume_total is not None]
    amounts = [decimal_value(item.sales_amount_total) for item in profiles if item.sales_amount_total is not None]
    prices = [decimal_value(item.price_wavg) for item in profiles if item.price_wavg is not None]
    return {
        "bucket_type": bucket_type,
        "bucket_code": code,
        "bucket_label": label,
        "sku_count": len(profiles),
        "valid_volume_sku_count": len(volumes),
        "total_sales_volume": decimal_to_float(sum(volumes, Decimal("0"))) if volumes else None,
        "total_sales_amount": decimal_to_float(sum(amounts, Decimal("0"))) if amounts else None,
        "median_price": decimal_to_float(decimal_median(prices)),
        "median_volume": decimal_to_float(decimal_median(volumes)),
        "median_amount": decimal_to_float(decimal_median(amounts)),
        "sample_status": sample_status_from_count(len(profiles)),
        "sku_codes": visible_skus,
        "sku_codes_returned": len(visible_skus),
        "sku_codes_truncated": sku_limit != 0 and len(sku_codes) > len(visible_skus),
        "top_skus": [
            {
                "sku_code": item.sku_code,
                "model_name": item.model_name,
                "sales_volume_total": decimal_to_float(item.sales_volume_total),
                "sales_amount_total": decimal_to_float(item.sales_amount_total),
                "price_wavg": decimal_to_float(item.price_wavg),
            }
            for item in sorted_profiles[: min(len(sorted_profiles), 10)]
        ],
    }


def decimal_value(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def decimal_sort_value(value: Any) -> Decimal:
    if value is None:
        return Decimal("-1")
    return decimal_value(value)


def decimal_median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(str(median(values)))


def sample_status_from_count(count: int) -> str:
    if count >= 6:
        return "sufficient"
    if count >= 3:
        return "limited"
    if count > 0:
        return "insufficient"
    return "unknown"


def should_route_to_value_battlefield_query(question: str, normalized: str) -> bool:
    return "价值战场" in question or "战场图谱" in question or "战场预设" in question or "battlefield" in normalized


def should_route_to_value_battlefield_coverage(question: str, normalized: str) -> bool:
    if any(word in question for word in ("覆盖", "哪些 SKU", "有哪些 SKU", "sku列表", "SKU列表")):
        return True
    return any(token in normalized for token in ("拖后腿", "机会战场", "主战场sku", "辅战场sku"))


def value_battlefield_relation_from_question(question: str) -> str:
    normalized = normalize_token(question)
    if "拖后腿" in normalized or "负向" in normalized:
        return "drag_factor_battlefield"
    if "主战场" in normalized:
        return "primary_battlefield"
    if "辅战场" in normalized:
        return "secondary_battlefield"
    if "机会" in normalized:
        return "opportunity_battlefield"
    if "厂家" in normalized or "主打" in normalized:
        return "brand_claimed_battlefield"
    if "用户观察" in normalized:
        return "user_observed_battlefield"
    return "all"


def should_route_to_comment_query(question: str, normalized: str) -> bool:
    return any(
        token in normalized
        for token in (
            "评论画像",
            "评论事实",
            "用户评价",
            "评价画像",
            "评价事实",
            "评论维度",
            "品牌力",
            "复购",
            "口碑",
        )
    ) or ("评论" in question and any(token in normalized for token in ("sku", "画像", "覆盖", "维度", "评价")))


def should_route_to_comment_coverage(question: str, normalized: str) -> bool:
    if any(word in question for word in ("覆盖", "哪些 SKU", "有哪些 SKU", "sku列表", "SKU列表")):
        return True
    return any(
        token in normalized
        for token in (
            "品牌力",
            "复购",
            "本品牌信任",
            "用户任务",
            "目标客群",
            "人群",
            "用途",
            "竞品对比",
            "参数支撑",
            "卖点支撑",
            "负面评价",
        )
    )


def should_route_to_market_query(question: str, normalized: str) -> bool:
    return any(
        token in normalized
        for token in (
            "市场画像",
            "市场情况",
            "量价",
            "销量位置",
            "价格区间",
            "尺寸区间",
            "价格带",
            "价位",
            "同价位",
            "可比池",
            "市场池",
        )
    )


def should_route_to_market_bucket_coverage(question: str, normalized: str) -> bool:
    if any(token in normalized for token in ("价格区间", "尺寸区间", "价格带", "价位", "同价位", "销量位置")):
        return True
    return any(word in question for word in ("覆盖", "哪些 SKU", "有哪些 SKU", "sku列表", "SKU列表")) and any(
        token in normalized for token in ("市场", "价格", "尺寸", "量价")
    )


def should_route_to_comparable_pools(question: str, normalized: str) -> bool:
    return any(token in normalized for token in ("可比池", "市场池", "同尺寸池", "同价池", "同价格带"))


def market_bucket_type_from_question(question: str, normalized: str) -> str:
    if "价格" in normalized and "尺寸" in normalized:
        return "size_price"
    if "尺寸" in normalized:
        return "size"
    if "价格" in normalized or "价位" in normalized:
        return "price"
    return "all"


def should_skip_negative_tier_match(query_text: str, item: M03BTierDefinition) -> bool:
    query_norm = normalize_token(query_text)
    if any(token in query_norm for token in ("无", "没有", "不具备", "none")):
        return False
    negative_tier_codes = {"health_none", "smart_ac_none", "comfort_basic"}
    positive_terms = {
        "health": ("新风", "净化"),
        "smart": ("wifi", "智能", "语音", "感应"),
        "comfort": ("舒适风", "自清洁"),
    }
    if item.tier_code not in negative_tier_codes:
        return False
    return any(normalize_token(term) in query_norm for term in positive_terms.get(item.dimension_code, ()))


def should_route_to_tier_coverage(question: str, normalized: str) -> bool:
    if any(word in question for word in ("档位", "覆盖", "有哪些 SKU", "哪些 SKU", "sku列表", "SKU列表")):
        return True
    tier_words = ("miniled", "oled", "lcd", "qled", "旗舰画质", "高端画质", "一级能效", "巨幕", "无分区", "挂机", "柜机", "新风", "舒适风", "自清洁", "循环风量", "匹")
    return any(word in normalized for word in tier_words)


def should_route_to_claim_position_coverage(question: str, normalized: str) -> bool:
    if any(word in question for word in ("覆盖", "哪些 SKU", "有哪些 SKU", "sku列表", "SKU列表", "位置")):
        return True
    position_words = (
        "miniled复合",
        "旗舰画质",
        "高阶显示",
        "画质增强",
        "电竞游戏",
        "游戏准备",
        "ai语音",
        "全屋互联",
        "家庭影院",
        "壁画贴墙",
        "轻薄全面屏",
        "芯片存储",
    )
    return any(word in normalized for word in position_words)


def extract_sku_or_model_query(question: str) -> str | None:
    sku_match = re.search(r"\b[A-Z]{1,4}\d{4,}\b", question.upper())
    if sku_match:
        return sku_match.group(0)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_+\-]*", question)
    for token in tokens:
        if any(char.isdigit() for char in token) and len(token) >= 3:
            return token
    return None


def extract_taxonomy_search(question: str, *, product_category: str = "TV") -> str | None:
    for marker in ("查", "看", "搜索"):
        if marker in question:
            tail = question.split(marker, 1)[1].strip()
            for suffix in ("标准参数", "参数表", "参数分类"):
                tail = tail.replace(suffix, "").strip()
            category_words = {"彩电", "电视", "tv"} if product_category == "TV" else {"空调", "ac"}
            return None if normalize_token(tail) in {normalize_token(item) for item in category_words} else tail or None
    return None


def extract_claim_taxonomy_search(question: str) -> str | None:
    for marker in ("查", "看", "搜索"):
        if marker in question:
            tail = question.split(marker, 1)[1].strip()
            for suffix in ("标准卖点", "卖点分类", "卖点维度", "卖点体系"):
                tail = tail.replace(suffix, "").strip()
            category_words = {"彩电", "电视", "tv"}
            return None if normalize_token(tail) in {normalize_token(item) for item in category_words} else tail or None
    return None


def normalize_product_category_arg(value: str | None) -> str:
    normalized = normalize_token(value or "TV")
    if normalized in {"tv", "彩电", "电视"}:
        return "TV"
    if normalized in {"ac", "空调"}:
        return "AC"
    raise CatForgeInsightError(f"不支持的产品品类：{value}")


def resolve_product_category(
    value: str | None,
    *,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    dimension: str | None = None,
    tier: str | None = None,
) -> str:
    normalized = normalize_token(value or "auto")
    if normalized != "auto":
        return normalize_product_category_arg(value)
    text = " ".join(item for item in (query, sku_code, model_name, dimension, tier) if item)
    text_norm = normalize_token(text)
    if "空调" in text_norm or re.search(r"\bAC\d{4,}\b", text.upper()):
        return "AC"
    if "彩电" in text_norm or "电视" in text_norm or re.search(r"\bTV\d{4,}\b", text.upper()):
        return "TV"
    return "TV"


def product_category_config(product_category: str) -> dict[str, Any]:
    normalized = normalize_product_category_arg(product_category)
    return PRODUCT_CATEGORY_CONFIGS[normalized]


def ensure_claim_taxonomy_available(product_category: str) -> None:
    config = product_category_config(product_category)
    if not config.get("claim_taxonomy_factory") or not config.get("claim_rule_version"):
        raise CatForgeInsightError(f"{config['label_cn']}标准卖点 taxonomy 尚未发布，不能查询 SKU 卖点事实画像。")


def claim_taxonomy_for_product_category(product_category: str) -> M04CClaimTaxonomy:
    ensure_claim_taxonomy_available(product_category)
    return product_category_config(product_category)["claim_taxonomy_factory"]()


def ensure_comment_taxonomy_available(product_category: str) -> None:
    config = product_category_config(product_category)
    if not config.get("comment_taxonomy_factory") or not config.get("comment_rule_version"):
        raise CatForgeInsightError(f"{config['label_cn']}评论事实 taxonomy 尚未发布，不能查询 SKU 评论事实画像。")


def comment_taxonomy_for_product_category(product_category: str) -> M05CCommentTaxonomy:
    ensure_comment_taxonomy_available(product_category)
    return product_category_config(product_category)["comment_taxonomy_factory"]()


def taxonomy_for_product_category(product_category: str) -> M03BTaxonomy:
    return product_category_config(product_category)["taxonomy_factory"]()


def normalize_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def extract_match_tokens(value: str) -> list[str]:
    stopwords = {
        "查",
        "看",
        "一下",
        "哪些",
        "哪个",
        "档位",
        "覆盖",
        "覆盖sku",
        "sku",
        "sku列表",
        "有哪些",
        "的",
        "是",
        "有",
        "多少",
        "彩电",
        "电视",
        "空调",
    }
    raw_tokens = re.findall(r"[A-Za-z0-9+\-]+|[\u4e00-\u9fff]+", value)
    tokens = []
    for raw_token in raw_tokens:
        token = normalize_token(raw_token)
        if not token or token in stopwords:
            continue
        for stopword in sorted(stopwords, key=len, reverse=True):
            token = token.replace(normalize_token(stopword), "")
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def decimal_to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def emit_result(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(render_text(result))


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def render_text(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status != "ok":
        return result.get("message_cn") or result.get("error") or json.dumps(to_jsonable(result), ensure_ascii=False)
    if "claim_summary" in result:
        sku = result["sku"]
        summary = result["claim_summary"]
        lines = [
            f"SKU 卖点事实画像：{sku.get('model_name') or '-'} / {sku.get('sku_code')}",
            f"批次：{result['batch_id']}；原始卖点：{summary['raw_claim_count']}；匹配卖点：{summary['matched_claim_count']}；事实卖点：{summary['fact_claim_count']}；参数未知：{summary['param_unknown_claim_count']}；参数不支撑：{summary['unsupported_claim_count']}；服务履约：{summary['service_separate_claim_count']}",
            "卖点位置：",
        ]
        for item in result.get("positions", []):
            lines.append(f"- {item['position_source']} / {item['dimension_code']}: {item['position_name']} ({item['position_code']})")
        if result.get("quality_flags"):
            lines.append("质量标记：" + ", ".join(result["quality_flags"]))
        return "\n".join(lines)
    if "comment_summary" in result:
        sku = result["sku"]
        summary = result["comment_summary"]
        lines = [
            f"SKU 评论事实画像：{sku.get('model_name') or '-'} / {sku.get('sku_code')}",
            f"批次：{result['batch_id']}；评论句：{summary['comment_sentence_count']}；命中句：{summary['matched_sentence_count']}；事实 atom：{summary['fact_atom_count']}；正向：{summary['positive_sentence_count']}；负向：{summary['negative_sentence_count']}；服务排除：{summary['service_excluded_sentence_count']}；需复核：{summary['review_required_count']}",
            "评论维度：",
        ]
        for dimension_code, item in (result.get("dimension_summary") or {}).items():
            lines.append(
                f"- {dimension_code}: {item.get('fact_atom_count', 0)} 条；正负={item.get('polarity_counts', {})}；子维度={', '.join(item.get('subdimension_codes', []))}"
            )
        if result.get("quality_flags"):
            lines.append("质量标记：" + ", ".join(result["quality_flags"]))
        return "\n".join(lines)
    if "market_metrics" in result:
        sku = result["sku"]
        metrics = result["market_metrics"]
        price_position = result["price_position"]
        size_position = result["size_position"]
        bucket = result.get("business_bucket_position") or {}
        quality = result["quality"]
        lines = [
            f"SKU 市场画像：{sku.get('model_name') or '-'} / {sku.get('sku_code')}",
            f"批次：{result['batch_id']}；窗口：{result['analysis_window']}；销量：{metrics.get('sales_volume_total')}；销额：{metrics.get('sales_amount_total')}；加权均价：{metrics.get('price_wavg')}",
            f"价格位置：{bucket.get('price_bucket_label') or price_position.get('price_band_category')}；品类价格分位：{price_position.get('price_percentile_in_category')}；品类销量分位：{price_position.get('volume_percentile_in_category')}",
            f"尺寸位置：{bucket.get('size_bucket_label') or size_position.get('size_segment')}；同尺寸销量分位：{price_position.get('volume_percentile_in_size')}；同池 SKU 数：{price_position.get('same_pool_sku_count')}",
            f"样本状态：{quality.get('sample_status')}；置信度：{quality.get('market_confidence')}",
        ]
        if result.get("signals"):
            lines.append(f"市场信号：{len(result['signals'])} 条")
        if result.get("comparable_pools"):
            lines.append(f"可比池：{len(result['comparable_pools'])} 个")
        if quality.get("quality_flags"):
            lines.append("质量标记：" + ", ".join(quality["quality_flags"]))
        return "\n".join(lines)
    if "pools" in result:
        sku = result["sku"]
        lines = [
            f"SKU 可比池：{sku.get('model_name') or '-'} / {sku.get('sku_code')}",
            f"批次：{result['batch_id']}；窗口：{result['analysis_window']}；可比池：{result['pool_count']} 个",
        ]
        for item in result["pools"]:
            sku_codes = ", ".join(item["candidate_sku_codes"]) if item["candidate_sku_codes"] else "-"
            suffix = "（已截断）" if item["candidate_sku_codes_truncated"] else ""
            lines.append(
                f"- {item['pool_type']}: {item['pool_sku_count']} 个 SKU；样本={item['sample_status']}；SKU：{sku_codes}{suffix}"
            )
        return "\n".join(lines)
    if "sku" in result:
        sku = result["sku"]
        summary = result["summary"]
        lines = [
            f"SKU 参数画像：{sku.get('model_name') or '-'} / {sku.get('sku_code')}",
            f"批次：{result['batch_id']}；完整度：{summary['param_completeness']:.2%}；已知参数：{summary['known_param_count']}；未知参数：{summary['unknown_param_count']}；冲突：{summary['conflict_count']}；需复核：{summary['review_required_count']}",
            "维度档位：",
        ]
        for item in result.get("dimension_tiers", []):
            lines.append(f"- {item['dimension_code']}: {item['tier_name']} ({item['tier_code']})")
        return "\n".join(lines)
    if "params" in result:
        label = result.get("product_category_label_cn") or result.get("category_code") or "品类"
        lines = [
            f"{label}标准参数：{result['param_count']}/{result['total_param_count']} 个；taxonomy={result['taxonomy_version']}",
            "分组数量：" + ", ".join(f"{key}={value}" for key, value in result["group_counts"].items()),
        ]
        for item in result["params"][:80]:
            raw_fields = ", ".join(item["raw_fields"]) or "-"
            core = "核心" if item["required_for_core"] else "辅助"
            lines.append(f"- {item['param_group']} / {item['param_code']} / {item['param_name']} / {core} / 原始字段：{raw_fields}")
        if len(result["params"]) > 80:
            lines.append(f"... 还有 {len(result['params']) - 80} 个参数，使用 --format json 查看完整结果。")
        return "\n".join(lines)
    if "claims" in result:
        label = result.get("product_category_label_cn") or result.get("category_code") or "品类"
        lines = [
            f"{label}标准卖点：{result['claim_count']}/{result['total_claim_count']} 个；taxonomy={result['taxonomy_version']}",
            "维度数量：" + ", ".join(f"{key}={value}" for key, value in result["dimension_counts"].items()),
        ]
        for item in result["claims"][:80]:
            support = ", ".join(item["support_param_codes"]) or "不按参数判断"
            kind = "服务履约单列" if item["service_separate"] else item["claim_kind"]
            lines.append(f"- {item['dimension_code']} / {item['claim_code']} / {item['claim_name']} / {kind} / 参数支撑：{support}")
        if len(result["claims"]) > 80:
            lines.append(f"... 还有 {len(result['claims']) - 80} 个卖点，使用 --format json 查看完整结果。")
        return "\n".join(lines)
    if "subdimensions" in result:
        label = result.get("product_category_label_cn") or result.get("category_code") or "品类"
        lines = [
            f"{label}评论事实维度：{result['subdimension_count']}/{result['total_subdimension_count']} 个；taxonomy={result['taxonomy_version']}",
            "维度数量：" + ", ".join(f"{key}={value}" for key, value in result["dimension_counts"].items()),
        ]
        for item in result["subdimensions"][:80]:
            params = ", ".join(item["linked_param_codes"]) or "-"
            claims = ", ".join(item["linked_claim_codes"]) or "-"
            lines.append(f"- {item['dimension_code']} / {item['subdimension_code']} / {item['subdimension_name']} / 参数：{params} / 卖点：{claims}")
        if len(result["subdimensions"]) > 80:
            lines.append(f"... 还有 {len(result['subdimensions']) - 80} 个评论子维度，使用 --format json 查看完整结果。")
        return "\n".join(lines)
    if result.get("bucket_source"):
        lines = [f"市场区间覆盖：批次 {result['batch_id']}，窗口 {result['analysis_window']}，命中 {result['coverage_count']} 个区间"]
        for item in result["coverages"]:
            sku_codes = ", ".join(item["sku_codes"]) if item["sku_codes"] else "-"
            suffix = "（已截断）" if item["sku_codes_truncated"] else ""
            lines.append(
                f"- {item['bucket_type']} / {item['bucket_label']} ({item['bucket_code']}): "
                f"{item['sku_count']} 个 SKU；总销量 {item['total_sales_volume']}；SKU：{sku_codes}{suffix}"
            )
        lines.append(result.get("bucket_source_note_cn", ""))
        return "\n".join(line for line in lines if line)
    if result.get("coverage_type") is not None:
        lines = [f"评论事实覆盖：批次 {result['batch_id']}，命中 {result['coverage_count']} 个覆盖项"]
        for item in result["coverages"]:
            sku_codes = ", ".join(item["sku_codes"]) if item["sku_codes"] else "-"
            suffix = "（已截断）" if item["sku_codes_truncated"] else ""
            lines.append(
                f"- {item['coverage_type']} / {item['coverage_name']} ({item['coverage_key']}): "
                f"{item['sku_count']} 个 SKU；正向 {item['positive_sentence_count']}；负向 {item['negative_sentence_count']}；SKU：{sku_codes}{suffix}"
            )
        return "\n".join(lines)
    if "coverages" in result:
        is_claim_coverage = "position_source" in result
        unit_name = "位置" if is_claim_coverage else "档位"
        lines = [f"{'卖点位置覆盖' if is_claim_coverage else '参数档位覆盖'}：批次 {result['batch_id']}，命中 {result['coverage_count']} 个{unit_name}"]
        for item in result["coverages"]:
            sku_codes = ", ".join(item["sku_codes"]) if item["sku_codes"] else "-"
            suffix = "（已截断）" if item["sku_codes_truncated"] else ""
            if "position_code" in item:
                lines.append(
                    f"- {item['position_source']} / {item['dimension_code']} / {item['position_name']} ({item['position_code']}): "
                    f"{item['sku_count']} 个 SKU，占比 {item['sku_ratio']:.2%}；SKU：{sku_codes}{suffix}"
                )
            else:
                lines.append(
                    f"- {item['dimension_code']} / {item['tier_name']} ({item['tier_code']}): "
                    f"{item['sku_count']} 个 SKU，占比 {item['sku_ratio']:.2%}；SKU：{sku_codes}{suffix}"
                )
        return "\n".join(lines)
    return json.dumps(to_jsonable(result), ensure_ascii=False, indent=2)


class CatForgeInsightError(Exception):
    """User-facing CLI error."""


if __name__ == "__main__":
    sys.exit(main())
