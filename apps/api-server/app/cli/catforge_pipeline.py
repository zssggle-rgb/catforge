"""Execution CLI for CatForge data-preparation and fact-profile jobs.

This module is intentionally small and agent-friendly. It exposes write actions
that natural-language agents can call without asking users to know module codes.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_DEFAULT_RULESET_VERSION,
    CORE3_M03B_AC_PARSER_VERSION,
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_PARSER_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_MODULE_VERSION,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
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
    Core3ModuleCode,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3PipelineTriggerType,
    Core3ReleaseGateStatus,
    Core3RunMode,
    Core3RunStatus,
    M07_ANALYSIS_WINDOWS,
)
from app.services.core3_real_data.m03b_param_profile_service import M03BRunner
from app.services.core3_real_data.m04c_claim_fact_profile_service import (
    INPUT_SOURCE_AUTO,
    M04CRunner,
)
from app.services.core3_real_data.m05c_comment_fact_profile_service import (
    LLM_MODE_AUTO,
    LLM_MODE_OFF,
    LLM_MODE_REQUIRED,
    M05C_DEFAULT_LLM_BATCH_SIZE,
    M05CRunner,
)
from app.services.core3_real_data.m09c_user_task_service import M09CRunner
from app.services.core3_real_data.m10c_target_group_service import M10CRunner
from app.services.core3_real_data.m11c_value_battlefield_service import M11CRunner
from app.services.core3_real_data.market_profile_runner import MarketProfileRunner
from app.services.core3_real_data.semantic_market_graph_service import (
    ANALYSIS_POPULATION_FACT_COMPLETE,
    MARKET_WINDOW_FULL_OBSERVED,
    M11DSemanticMarketRunner,
)
from app.services.core3_real_data.m12c_claim_value_quantification_runner import (
    M12CClaimValueQuantificationRunner,
)
from app.services.core3_real_data.m12c_claim_value_quantification_service import (
    ANALYSIS_POPULATION_READY_WITH_COMMENT,
)


DEFAULT_PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_CATEGORY_CODE = "TV"
LATEST_BATCH = "latest"
DEFAULT_M07_SKU_CHUNK_SIZE = 50
COMMENT_COVERAGE_AUTO = "auto"
COMMENT_COVERAGE_INLINE = "inline"
COMMENT_COVERAGE_SKIP = "skip"
COMMENT_COVERAGE_REBUILD_ONLY = "rebuild-only"
DEFAULT_COMMENT_BATCH_PARALLELISM = 2

PRODUCT_CATEGORY_CONFIGS = {
    "TV": {
        "label_cn": "彩电",
        "sku_code_prefix": "TV",
        "taxonomy_version": CORE3_M03B_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_PARSER_VERSION,
        "rule_version": CORE3_M03B_RULE_VERSION,
        "claim_taxonomy_version": CORE3_M04C_TV_TAXONOMY_VERSION,
        "claim_rule_version": CORE3_M04C_TV_RULE_VERSION,
        "comment_taxonomy_version": CORE3_M05C_TV_TAXONOMY_VERSION,
        "comment_rule_version": CORE3_M05C_TV_RULE_VERSION,
        "user_task_taxonomy_version": CORE3_M09C_TV_TAXONOMY_VERSION,
        "user_task_rule_version": CORE3_M09C_TV_RULE_VERSION,
        "target_group_taxonomy_version": CORE3_M10C_TV_TAXONOMY_VERSION,
        "target_group_rule_version": CORE3_M10C_TV_RULE_VERSION,
        "value_battlefield_taxonomy_version": CORE3_M11C_TV_TAXONOMY_VERSION,
        "value_battlefield_rule_version": CORE3_M11C_TV_RULE_VERSION,
        "semantic_market_rule_version": CORE3_M11D_RULE_VERSION,
        "claim_value_quantification_rule_version": CORE3_M12C_RULE_VERSION,
    },
    "AC": {
        "label_cn": "空调",
        "sku_code_prefix": "AC",
        "taxonomy_version": CORE3_M03B_AC_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_AC_PARSER_VERSION,
        "rule_version": CORE3_M03B_AC_RULE_VERSION,
        "claim_taxonomy_version": CORE3_M04C_AC_TAXONOMY_VERSION,
        "claim_rule_version": CORE3_M04C_AC_RULE_VERSION,
        "comment_taxonomy_version": CORE3_M05C_AC_TAXONOMY_VERSION,
        "comment_rule_version": CORE3_M05C_AC_RULE_VERSION,
        "user_task_taxonomy_version": CORE3_M09C_AC_TAXONOMY_VERSION,
        "user_task_rule_version": CORE3_M09C_AC_RULE_VERSION,
        "target_group_taxonomy_version": CORE3_M10C_AC_TAXONOMY_VERSION,
        "target_group_rule_version": CORE3_M10C_AC_RULE_VERSION,
        "value_battlefield_taxonomy_version": CORE3_M11C_AC_TAXONOMY_VERSION,
        "value_battlefield_rule_version": CORE3_M11C_AC_RULE_VERSION,
        "semantic_market_rule_version": None,
        "claim_value_quantification_rule_version": None,
    },
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            if args.command == "run-param-profile":
                result = run_param_profile(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-claim-profile":
                result = run_claim_profile(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    input_source=args.input_source,
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-market-profile":
                result = run_market_profile(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    sku_scope=args.sku_code or (),
                    analysis_windows=args.analysis_window or (),
                    sku_chunk_size=args.sku_chunk_size,
                )
            elif args.command == "run-comment-profile":
                result = run_comment_profile(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    sku_scope=args.sku_code or (),
                    max_sentences_per_sku=args.max_sentences_per_sku,
                    llm_mode=args.llm_mode,
                    llm_batch_size=args.llm_batch_size,
                    force_rebuild=args.force_rebuild,
                    coverage_mode=args.coverage_mode,
                )
            elif args.command == "run-comment-profile-batch":
                result = run_comment_profile_batch(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    sku_scope=args.sku_code or (),
                    exclude_sku_scope=args.exclude_sku_code or (),
                    max_sentences_per_sku=args.max_sentences_per_sku,
                    llm_mode=args.llm_mode,
                    llm_batch_size=args.llm_batch_size,
                    force_rebuild=args.force_rebuild,
                    parallelism=args.parallelism,
                    limit=args.limit,
                    rerun_existing=args.rerun_existing,
                    rebuild_coverage_at_end=not args.skip_final_coverage,
                )
            elif args.command == "run-user-task":
                result = run_user_task(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    sku_scope=args.sku_code or (),
                    user_task_codes=args.user_task_code or (),
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-target-group":
                result = run_target_group(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    sku_scope=args.sku_code or (),
                    target_group_codes=args.target_group_code or (),
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-value-battlefield":
                result = run_value_battlefield(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    sku_scope=args.sku_code or (),
                    battlefield_codes=args.battlefield_code or (),
                    graph_mode=args.graph_mode,
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-semantic-market-graph":
                result = run_semantic_market_graph(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    analysis_population=args.analysis_population,
                    market_window=args.market_window,
                    sku_scope=args.sku_code or (),
                    dimension_types=args.dimension_type or (),
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-claim-value-quantification":
                result = run_claim_value_quantification(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(
                        args.product_category
                    ),
                    analysis_population=args.analysis_population,
                    market_window=args.market_window,
                    sku_scope=args.sku_code or (),
                )
            elif args.command == "ask":
                result = answer_natural_language(
                    db,
                    question=" ".join(args.question),
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=args.product_category,
                    input_source=args.input_source,
                    max_sentences_per_sku=args.max_sentences_per_sku,
                    llm_mode=args.llm_mode,
                    llm_batch_size=args.llm_batch_size,
                    force_rebuild=args.force_rebuild,
                    coverage_mode=args.coverage_mode,
                    comment_parallelism=args.comment_parallelism,
                    comment_batch_limit=args.comment_batch_limit,
                    rerun_existing_comment=args.rerun_existing_comment,
                    rebuild_comment_coverage_at_end=not args.skip_comment_final_coverage,
                )
            else:
                parser.error("missing command")
                return 2
    except CatForgePipelineError as exc:
        result = {"status": "error", "error": str(exc)}
        emit_result(result, args.format)
        return 1

    emit_result(result, args.format)
    return 0 if result.get("status") in {"ok", "warning"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.catforge_pipeline",
        description="Run CatForge preparation/profile jobs using stable atomic commands or natural language.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_profile = subparsers.add_parser(
        "run-param-profile",
        help="Generate or rerun SKU parameter fact profiles for a product category.",
    )
    add_common_args(run_profile)
    add_product_category_arg(run_profile, default="tv", allow_auto=False)
    run_profile.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_profile)

    run_claim = subparsers.add_parser(
        "run-claim-profile",
        help="Generate or rerun SKU claim fact profiles for a product category.",
    )
    add_common_args(run_claim)
    add_product_category_arg(run_claim, default="tv", allow_auto=False)
    run_claim.add_argument(
        "--input-source",
        choices=("auto", "evidence", "clean", "raw"),
        default=INPUT_SOURCE_AUTO,
        help="Claim input source. auto prefers M02 evidence, then M01 clean claims, then raw selling_points_data.",
    )
    run_claim.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_claim)

    run_comment = subparsers.add_parser(
        "run-comment-profile",
        help="Generate or rerun SKU comment fact profiles for a product category.",
    )
    add_common_args(run_comment)
    add_product_category_arg(run_comment, default="tv", allow_auto=False)
    run_comment.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_comment.add_argument(
        "--max-sentences-per-sku",
        type=int,
        default=500,
        help="Maximum M02 comment sentences read per SKU to keep memory bounded.",
    )
    run_comment.add_argument(
        "--llm-mode",
        choices=(LLM_MODE_AUTO, LLM_MODE_REQUIRED, LLM_MODE_OFF),
        default=LLM_MODE_AUTO,
        help="LLM usage for comment semantic extraction. Use required on 205 validation to ensure the model is called.",
    )
    run_comment.add_argument(
        "--llm-batch-size",
        type=int,
        default=M05C_DEFAULT_LLM_BATCH_SIZE,
        help="Number of comment sentences per LLM request.",
    )
    run_comment.add_argument(
        "--coverage-mode",
        choices=(
            COMMENT_COVERAGE_AUTO,
            COMMENT_COVERAGE_INLINE,
            COMMENT_COVERAGE_SKIP,
            COMMENT_COVERAGE_REBUILD_ONLY,
        ),
        default=COMMENT_COVERAGE_AUTO,
        help="Comment coverage handling. auto skips coverage for SKU-scoped runs; rebuild-only recomputes batch coverage from saved comment facts.",
    )
    run_comment.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_comment)

    run_comment_batch = subparsers.add_parser(
        "run-comment-profile-batch",
        help="Run M05C comment fact profiles by SKU with bounded parallel workers.",
    )
    add_common_args(run_comment_batch)
    add_product_category_arg(run_comment_batch, default="tv", allow_auto=False)
    run_comment_batch.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_comment_batch.add_argument(
        "--exclude-sku-code",
        action="append",
        help="Optional SKU to exclude from this batch, useful when another worker is already running it.",
    )
    run_comment_batch.add_argument(
        "--max-sentences-per-sku",
        type=int,
        default=500,
        help="Maximum M02 comment sentences read per SKU to keep memory and LLM cost bounded.",
    )
    run_comment_batch.add_argument(
        "--llm-mode",
        choices=(LLM_MODE_AUTO, LLM_MODE_REQUIRED, LLM_MODE_OFF),
        default=LLM_MODE_AUTO,
        help="LLM usage for comment semantic extraction. Use required on 205 validation to ensure the model is called.",
    )
    run_comment_batch.add_argument(
        "--llm-batch-size",
        type=int,
        default=M05C_DEFAULT_LLM_BATCH_SIZE,
        help="Number of comment sentences per LLM request.",
    )
    run_comment_batch.add_argument(
        "--parallelism",
        type=int,
        default=DEFAULT_COMMENT_BATCH_PARALLELISM,
        help="Number of SKU workers to run concurrently. Start with 2 on 205 and increase only after observing stability.",
    )
    run_comment_batch.add_argument(
        "--limit",
        type=int,
        help="Maximum number of pending SKUs to schedule in this run. Useful for 205 smoke tests.",
    )
    run_comment_batch.add_argument(
        "--rerun-existing",
        action="store_true",
        help="Include SKUs that already have current M05C profiles. Use with --force-rebuild for full reruns.",
    )
    run_comment_batch.add_argument(
        "--skip-final-coverage",
        action="store_true",
        help="Do not rebuild batch-level M05C coverage after SKU workers finish.",
    )
    run_comment_batch.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_comment_batch)

    run_market = subparsers.add_parser(
        "run-market-profile",
        help="Generate or rerun SKU market profiles and comparable-pool baselines.",
    )
    add_common_args(run_market)
    add_product_category_arg(run_market, default="tv", allow_auto=False)
    run_market.add_argument(
        "--analysis-window",
        action="append",
        choices=(
            "full_observed_window",
            "latest_week",
            "recent_4w",
            "recent_8w",
            "recent_12w",
        ),
        help="Analysis window to run. Repeat for multiple windows. Default runs all M07 windows.",
    )
    run_market.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_market.add_argument(
        "--sku-chunk-size",
        type=int,
        default=DEFAULT_M07_SKU_CHUNK_SIZE,
        help="Number of SKUs per M07 execution chunk. Default keeps 205 memory below the API container limit.",
    )
    add_format_arg(run_market)

    run_value_battlefield = subparsers.add_parser(
        "run-value-battlefield",
        help="Generate or rerun SKU value battlefield profiles and graph snapshots.",
    )
    add_common_args(run_value_battlefield)
    add_product_category_arg(run_value_battlefield, default="tv", allow_auto=False)
    run_value_battlefield.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_value_battlefield.add_argument(
        "--battlefield-code",
        action="append",
        help="Optional battlefield scope. Repeat to run selected battlefields only.",
    )
    run_value_battlefield.add_argument(
        "--graph-mode",
        choices=("inline", "skip", "rebuild-only"),
        default="inline",
        help="Graph handling. inline rebuilds graph with SKU profiles; skip writes only SKU profiles/scores; rebuild-only writes graph for the selected scope.",
    )
    run_value_battlefield.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_value_battlefield)

    run_user_task = subparsers.add_parser(
        "run-user-task", help="Generate or rerun SKU user-task profiles and coverage."
    )
    add_common_args(run_user_task)
    add_product_category_arg(run_user_task, default="tv", allow_auto=False)
    run_user_task.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_user_task.add_argument(
        "--user-task-code",
        action="append",
        help="Optional user-task scope. Repeat to run selected user tasks only.",
    )
    run_user_task.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_user_task)

    run_target_group = subparsers.add_parser(
        "run-target-group",
        help="Generate or rerun SKU target-group profiles and coverage.",
    )
    add_common_args(run_target_group)
    add_product_category_arg(run_target_group, default="tv", allow_auto=False)
    run_target_group.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_target_group.add_argument(
        "--target-group-code",
        action="append",
        help="Optional target-group scope. Repeat to run selected target groups only.",
    )
    run_target_group.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(run_target_group)

    run_semantic_market = subparsers.add_parser(
        "run-semantic-market-graph",
        help="Generate M11D task/group/battlefield market graph and sales allocation results.",
    )
    add_common_args(run_semantic_market)
    add_product_category_arg(run_semantic_market, default="tv", allow_auto=False)
    run_semantic_market.add_argument(
        "--analysis-population",
        choices=("fact_complete_with_comment", "all_semantic_profiles"),
        default=ANALYSIS_POPULATION_FACT_COMPLETE,
        help="SKU population for semantic market graph.",
    )
    run_semantic_market.add_argument(
        "--market-window",
        choices=("full_observed_window", "recent_12w", "custom_week_range"),
        default=MARKET_WINDOW_FULL_OBSERVED,
        help="Market window for volume/amount allocation. v0.1 reads matching M07 market profiles.",
    )
    run_semantic_market.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    run_semantic_market.add_argument(
        "--dimension-type",
        action="append",
        choices=("user_task", "target_group", "battlefield"),
        help="Optional dimension type scope. Repeat to run selected dimensions only.",
    )
    run_semantic_market.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Mark current M11D outputs stale and write a fresh result set.",
    )
    add_format_arg(run_semantic_market)

    run_claim_value = subparsers.add_parser(
        "run-claim-value-quantification",
        help="Generate M12C claim value quantification and claim contribution attribution results.",
    )
    add_common_args(run_claim_value)
    add_product_category_arg(run_claim_value, default="tv", allow_auto=False)
    run_claim_value.add_argument(
        "--analysis-population",
        choices=("claim_value_ready_with_comment", "claim_value_ready"),
        default=ANALYSIS_POPULATION_READY_WITH_COMMENT,
        help="SKU population for claim value quantification.",
    )
    run_claim_value.add_argument(
        "--market-window",
        choices=("full_observed_window", "recent_12w", "custom_week_range"),
        default=MARKET_WINDOW_FULL_OBSERVED,
    )
    run_claim_value.add_argument(
        "--sku-code",
        action="append",
        help="Optional SKU scope. Repeat to run selected SKUs only.",
    )
    add_format_arg(run_claim_value)

    ask = subparsers.add_parser(
        "ask", help="Route a natural-language execution request."
    )
    add_common_args(ask)
    add_product_category_arg(ask)
    ask.add_argument("question", nargs="+", help="Natural-language execution request.")
    ask.add_argument(
        "--input-source",
        choices=("auto", "evidence", "clean", "raw"),
        default=INPUT_SOURCE_AUTO,
        help="Claim input source when the natural-language request routes to claim profile generation.",
    )
    ask.add_argument(
        "--max-sentences-per-sku",
        type=int,
        default=500,
        help="Maximum M02 comment sentences read per SKU when routed to comment fact generation.",
    )
    ask.add_argument(
        "--llm-mode",
        choices=(LLM_MODE_AUTO, LLM_MODE_REQUIRED, LLM_MODE_OFF),
        default=LLM_MODE_AUTO,
        help="LLM usage when routed to comment fact generation.",
    )
    ask.add_argument(
        "--llm-batch-size",
        type=int,
        default=M05C_DEFAULT_LLM_BATCH_SIZE,
        help="Comment sentences per LLM request when routed to comment fact generation.",
    )
    ask.add_argument(
        "--comment-parallelism",
        type=int,
        default=DEFAULT_COMMENT_BATCH_PARALLELISM,
        help="Parallel SKU worker count when natural language routes to comment batch generation.",
    )
    ask.add_argument(
        "--comment-batch-limit",
        type=int,
        help="Maximum pending SKUs when natural language routes to comment batch generation.",
    )
    ask.add_argument(
        "--rerun-existing-comment",
        action="store_true",
        help="Include existing M05C comment profiles when natural language routes to comment batch generation.",
    )
    ask.add_argument(
        "--skip-comment-final-coverage",
        action="store_true",
        help="Skip final M05C coverage rebuild when natural language routes to comment batch generation.",
    )
    ask.add_argument(
        "--coverage-mode",
        choices=(
            COMMENT_COVERAGE_AUTO,
            COMMENT_COVERAGE_INLINE,
            COMMENT_COVERAGE_SKIP,
            COMMENT_COVERAGE_REBUILD_ONLY,
        ),
        default=COMMENT_COVERAGE_AUTO,
        help="Comment coverage handling when routed to comment fact generation.",
    )
    ask.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Replace same business-key outputs if hashes changed.",
    )
    add_format_arg(ask)
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument(
        "--category-code",
        default=DEFAULT_CATEGORY_CODE,
        help="Current source-batch category code. The 205 mixed TV/AC batch uses TV.",
    )
    parser.add_argument("--batch-id", default=LATEST_BATCH)


def add_product_category_arg(
    parser: argparse.ArgumentParser, *, default: str = "auto", allow_auto: bool = True
) -> None:
    choices = ("auto", "tv", "ac") if allow_auto else ("tv", "ac")
    parser.add_argument("--product-category", choices=choices, default=default)


def add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="text")


def answer_natural_language(
    db: Session,
    *,
    question: str,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    force_rebuild: bool,
    input_source: str = INPUT_SOURCE_AUTO,
    max_sentences_per_sku: int = 500,
    llm_mode: str = LLM_MODE_AUTO,
    llm_batch_size: int = M05C_DEFAULT_LLM_BATCH_SIZE,
    coverage_mode: str = COMMENT_COVERAGE_AUTO,
    comment_parallelism: int = DEFAULT_COMMENT_BATCH_PARALLELISM,
    comment_batch_limit: int | None = None,
    rerun_existing_comment: bool = False,
    rebuild_comment_coverage_at_end: bool = True,
) -> dict[str, Any]:
    resolved_product_category = resolve_product_category(
        product_category, question=question
    )
    if should_run_semantic_market_graph(question):
        result = run_semantic_market_graph(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            analysis_population=ANALYSIS_POPULATION_FACT_COMPLETE,
            market_window=MARKET_WINDOW_FULL_OBSERVED,
            sku_scope=extract_sku_scope(question),
            dimension_types=extract_semantic_dimension_types(question),
            force_rebuild=force_rebuild,
        )
        result["question"] = question
        result["routed_command"] = "run-semantic-market-graph"
        return result
    if should_run_claim_value_quantification(question):
        result = run_claim_value_quantification(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            analysis_population=ANALYSIS_POPULATION_READY_WITH_COMMENT,
            market_window=MARKET_WINDOW_FULL_OBSERVED,
            sku_scope=extract_sku_scope(question),
        )
        result["question"] = question
        result["routed_command"] = "run-claim-value-quantification"
        return result
    if should_run_user_task(question):
        result = run_user_task(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            sku_scope=extract_sku_scope(question),
            user_task_codes=extract_user_task_scope(question),
            force_rebuild=force_rebuild,
        )
        result["question"] = question
        result["routed_command"] = "run-user-task"
        return result
    if should_run_target_group(question):
        result = run_target_group(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            sku_scope=extract_sku_scope(question),
            target_group_codes=extract_target_group_scope(question),
            force_rebuild=force_rebuild,
        )
        result["question"] = question
        result["routed_command"] = "run-target-group"
        return result
    if should_run_value_battlefield(question):
        result = run_value_battlefield(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            sku_scope=extract_sku_scope(question),
            battlefield_codes=extract_battlefield_scope(question),
            graph_mode="inline",
            force_rebuild=force_rebuild,
        )
        result["question"] = question
        result["routed_command"] = "run-value-battlefield"
        return result
    if should_run_comment_profile(question):
        sku_scope = extract_sku_scope(question)
        if should_run_comment_profile_batch(question) or (
            not sku_scope and should_continue_unscoped_comment_batch(question)
        ):
            result = run_comment_profile_batch(
                db,
                project_id=project_id,
                source_category_code=source_category_code,
                batch_id=batch_id,
                product_category=resolved_product_category,
                sku_scope=sku_scope,
                max_sentences_per_sku=max_sentences_per_sku,
                llm_mode=llm_mode,
                llm_batch_size=llm_batch_size,
                force_rebuild=force_rebuild,
                parallelism=comment_parallelism,
                limit=comment_batch_limit,
                rerun_existing=rerun_existing_comment,
                rebuild_coverage_at_end=rebuild_comment_coverage_at_end,
            )
            result["question"] = question
            result["routed_command"] = "run-comment-profile-batch"
            return result
        result = run_comment_profile(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            sku_scope=sku_scope,
            max_sentences_per_sku=max_sentences_per_sku,
            llm_mode=llm_mode,
            llm_batch_size=llm_batch_size,
            force_rebuild=force_rebuild,
            coverage_mode=coverage_mode,
        )
        result["question"] = question
        result["routed_command"] = "run-comment-profile"
        return result
    if should_run_market_profile(question):
        result = run_market_profile(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            sku_scope=extract_sku_scope(question),
            analysis_windows=extract_analysis_windows(question),
        )
        result["question"] = question
        result["routed_command"] = "run-market-profile"
        return result
    if should_run_claim_profile(question):
        result = run_claim_profile(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            input_source=input_source,
            force_rebuild=force_rebuild,
        )
        result["question"] = question
        result["routed_command"] = "run-claim-profile"
        return result
    if not should_run_param_profile(question):
        raise CatForgePipelineError(
            "当前执行 CLI 只支持生成/重跑 SKU 参数画像、卖点事实画像、评论事实画像、市场画像、用户任务画像、目标客群画像、价值战场画像、M11D 语义市场图谱或 M12C 卖点价值量化。请说明要生成或重新生成哪类画像。"
        )
    result = run_param_profile(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=batch_id,
        product_category=resolved_product_category,
        force_rebuild=force_rebuild,
    )
    result["question"] = question
    result["routed_command"] = "run-param-profile"
    return result


def run_user_task(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_scope: Sequence[str] = (),
    user_task_codes: Sequence[str] = (),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    if not config.get("user_task_taxonomy_version") or not config.get(
        "user_task_rule_version"
    ):
        raise CatForgePipelineError(
            f"{config['label_cn']}用户任务 taxonomy 尚未发布，不能生成 SKU 用户任务画像。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M09CRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        taxonomy_version=config["user_task_taxonomy_version"],
        rule_version=config["user_task_rule_version"],
        target_sku_codes=sku_scope,
        user_task_codes=user_task_codes,
        force_rebuild=force_rebuild,
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "sku_scope": list(sku_scope),
        "user_task_codes": list(user_task_codes),
        "taxonomy_version": config["user_task_taxonomy_version"],
        "rule_version": config["user_task_rule_version"],
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_target_group(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_scope: Sequence[str] = (),
    target_group_codes: Sequence[str] = (),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    if not config.get("target_group_taxonomy_version") or not config.get(
        "target_group_rule_version"
    ):
        raise CatForgePipelineError(
            f"{config['label_cn']}目标客群 taxonomy 尚未发布，不能生成 SKU 目标客群画像。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M10CRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        taxonomy_version=config["target_group_taxonomy_version"],
        rule_version=config["target_group_rule_version"],
        target_sku_codes=sku_scope,
        target_group_codes=target_group_codes,
        force_rebuild=force_rebuild,
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "sku_scope": list(sku_scope),
        "target_group_codes": list(target_group_codes),
        "taxonomy_version": config["target_group_taxonomy_version"],
        "rule_version": config["target_group_rule_version"],
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_value_battlefield(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_scope: Sequence[str] = (),
    battlefield_codes: Sequence[str] = (),
    graph_mode: str = "inline",
    force_rebuild: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    if not config.get("value_battlefield_taxonomy_version") or not config.get(
        "value_battlefield_rule_version"
    ):
        raise CatForgePipelineError(
            f"{config['label_cn']}价值战场 taxonomy 尚未发布，不能生成 SKU 价值战场画像。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M11CRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        taxonomy_version=config["value_battlefield_taxonomy_version"],
        rule_version=config["value_battlefield_rule_version"],
        target_sku_codes=sku_scope,
        battlefield_codes=battlefield_codes,
        force_rebuild=force_rebuild,
        graph_mode=graph_mode,
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "sku_scope": list(sku_scope),
        "battlefield_codes": list(battlefield_codes),
        "graph_mode": graph_mode,
        "taxonomy_version": config["value_battlefield_taxonomy_version"],
        "rule_version": config["value_battlefield_rule_version"],
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_semantic_market_graph(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    analysis_population: str = ANALYSIS_POPULATION_FACT_COMPLETE,
    market_window: str = MARKET_WINDOW_FULL_OBSERVED,
    sku_scope: Sequence[str] = (),
    dimension_types: Sequence[str] = (),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    if not config.get("semantic_market_rule_version"):
        raise CatForgePipelineError(
            f"{config['label_cn']}语义市场图谱规则尚未发布，不能生成 M11D 结果。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M11DSemanticMarketRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        analysis_population=analysis_population,
        market_window=market_window,
        target_sku_codes=sku_scope,
        dimension_types=dimension_types,
        rule_version=config["semantic_market_rule_version"],
        force_rebuild=force_rebuild,
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "analysis_population": analysis_population,
        "market_window": market_window,
        "sku_scope": list(sku_scope),
        "dimension_types": list(dimension_types),
        "rule_version": config["semantic_market_rule_version"],
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_claim_value_quantification(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    analysis_population: str = ANALYSIS_POPULATION_READY_WITH_COMMENT,
    market_window: str = MARKET_WINDOW_FULL_OBSERVED,
    sku_scope: Sequence[str] = (),
) -> dict[str, Any]:
    config = product_category_config(product_category)
    if not config.get("claim_value_quantification_rule_version"):
        raise CatForgePipelineError(
            f"{config['label_cn']}卖点价值量化规则尚未发布，不能生成 M12C 结果。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M12CClaimValueQuantificationRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        analysis_population=analysis_population,
        market_window=market_window,
        target_sku_codes=sku_scope,
        rule_version=config["claim_value_quantification_rule_version"],
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "analysis_population": analysis_population,
        "market_window": market_window,
        "sku_scope": list(sku_scope),
        "rule_version": config["claim_value_quantification_rule_version"],
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_comment_profile(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_scope: Sequence[str] = (),
    max_sentences_per_sku: int = 500,
    llm_mode: str = LLM_MODE_AUTO,
    llm_batch_size: int = M05C_DEFAULT_LLM_BATCH_SIZE,
    force_rebuild: bool = False,
    coverage_mode: str = COMMENT_COVERAGE_AUTO,
) -> dict[str, Any]:
    if max_sentences_per_sku <= 0:
        raise CatForgePipelineError("M05C 每个 SKU 的评论句子读取上限必须大于 0。")
    if llm_batch_size <= 0:
        raise CatForgePipelineError("M05C LLM 批大小必须大于 0。")
    config = product_category_config(product_category)
    if not config.get("comment_taxonomy_version") or not config.get(
        "comment_rule_version"
    ):
        raise CatForgePipelineError(
            f"{config['label_cn']}评论事实 taxonomy 尚未发布，不能生成 SKU 评论事实画像。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    if coverage_mode == COMMENT_COVERAGE_REBUILD_ONLY:
        module_result = M05CRunner(db).rebuild_coverage(
            project_id=project_id,
            category_code=source_category_code,
            batch_id=resolved_batch_id,
            product_category=product_category,
            taxonomy_version=config["comment_taxonomy_version"],
            rule_version=config["comment_rule_version"],
            force_rebuild=True,
        )
    else:
        build_coverage = coverage_mode == COMMENT_COVERAGE_INLINE or (
            coverage_mode == COMMENT_COVERAGE_AUTO and not sku_scope
        )
        module_result = M05CRunner(db).run_batch(
            project_id=project_id,
            category_code=source_category_code,
            batch_id=resolved_batch_id,
            product_category=product_category,
            taxonomy_version=config["comment_taxonomy_version"],
            rule_version=config["comment_rule_version"],
            target_sku_codes=sku_scope,
            max_sentences_per_sku=max_sentences_per_sku,
            llm_mode=llm_mode,
            llm_batch_size=llm_batch_size,
            force_rebuild=force_rebuild,
            build_coverage=build_coverage,
        )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "sku_scope": list(sku_scope),
        "max_sentences_per_sku": max_sentences_per_sku,
        "llm_mode": llm_mode,
        "llm_batch_size": llm_batch_size,
        "coverage_mode": coverage_mode,
        "taxonomy_version": config["comment_taxonomy_version"],
        "rule_version": config["comment_rule_version"],
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_comment_profile_batch(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_scope: Sequence[str] = (),
    exclude_sku_scope: Sequence[str] = (),
    max_sentences_per_sku: int = 500,
    llm_mode: str = LLM_MODE_AUTO,
    llm_batch_size: int = M05C_DEFAULT_LLM_BATCH_SIZE,
    force_rebuild: bool = False,
    parallelism: int = DEFAULT_COMMENT_BATCH_PARALLELISM,
    limit: int | None = None,
    rerun_existing: bool = False,
    rebuild_coverage_at_end: bool = True,
    session_factory: Any | None = None,
) -> dict[str, Any]:
    if max_sentences_per_sku <= 0:
        raise CatForgePipelineError("M05C 每个 SKU 的评论句子读取上限必须大于 0。")
    if llm_batch_size <= 0:
        raise CatForgePipelineError("M05C LLM 批大小必须大于 0。")
    if parallelism <= 0:
        raise CatForgePipelineError("M05C 并发 worker 数必须大于 0。")
    if limit is not None and limit <= 0:
        raise CatForgePipelineError("M05C 批量执行 limit 必须大于 0。")
    config = product_category_config(product_category)
    if not config.get("comment_taxonomy_version") or not config.get(
        "comment_rule_version"
    ):
        raise CatForgePipelineError(
            f"{config['label_cn']}评论事实 taxonomy 尚未发布，不能生成 SKU 评论事实画像。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    plan = plan_comment_profile_batch_skus(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        sku_code_prefix=str(config["sku_code_prefix"]),
        taxonomy_version=str(config["comment_taxonomy_version"]),
        rule_version=str(config["comment_rule_version"]),
        sku_scope=sku_scope,
        exclude_sku_scope=exclude_sku_scope,
        rerun_existing=rerun_existing,
        limit=limit,
    )

    worker_session_factory = session_factory or SessionLocal
    scheduled_skus = list(plan["scheduled_sku_codes"])
    sku_results: list[dict[str, Any]] = []
    if scheduled_skus:
        db.rollback()
        if parallelism == 1 or len(scheduled_skus) == 1:
            for sku_code in scheduled_skus:
                sku_results.append(
                    run_comment_profile_batch_worker(
                        session_factory=worker_session_factory,
                        project_id=project_id,
                        source_category_code=source_category_code,
                        batch_id=resolved_batch_id,
                        product_category=product_category,
                        sku_code=sku_code,
                        taxonomy_version=str(config["comment_taxonomy_version"]),
                        rule_version=str(config["comment_rule_version"]),
                        max_sentences_per_sku=max_sentences_per_sku,
                        llm_mode=llm_mode,
                        llm_batch_size=llm_batch_size,
                        force_rebuild=force_rebuild,
                        rerun_existing=rerun_existing,
                    )
                )
        else:
            with ThreadPoolExecutor(
                max_workers=min(parallelism, len(scheduled_skus))
            ) as executor:
                futures = {
                    executor.submit(
                        run_comment_profile_batch_worker,
                        session_factory=worker_session_factory,
                        project_id=project_id,
                        source_category_code=source_category_code,
                        batch_id=resolved_batch_id,
                        product_category=product_category,
                        sku_code=sku_code,
                        taxonomy_version=str(config["comment_taxonomy_version"]),
                        rule_version=str(config["comment_rule_version"]),
                        max_sentences_per_sku=max_sentences_per_sku,
                        llm_mode=llm_mode,
                        llm_batch_size=llm_batch_size,
                        force_rebuild=force_rebuild,
                        rerun_existing=rerun_existing,
                    ): sku_code
                    for sku_code in scheduled_skus
                }
                for future in as_completed(futures):
                    try:
                        sku_results.append(future.result())
                    except Exception as exc:  # pragma: no cover - defensive; worker already catches expected failures.
                        sku_results.append(
                            {
                                "sku_code": futures[future],
                                "status": "error",
                                "module_status": "failed",
                                "error": str(exc),
                            }
                        )
        sku_results.sort(key=lambda item: str(item.get("sku_code") or ""))

    completed_results = [
        item for item in sku_results if item.get("status") in {"ok", "warning"}
    ]
    failed_results = [item for item in sku_results if item.get("status") == "error"]
    skipped_results = [item for item in sku_results if item.get("status") == "skipped"]
    final_coverage_result: dict[str, Any] | None = None
    should_rebuild_coverage = rebuild_coverage_at_end and (
        bool(completed_results) or bool(plan["existing_profile_sku_codes"])
    )
    if should_rebuild_coverage:
        final_coverage_result = run_comment_profile(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=resolved_batch_id,
            product_category=product_category,
            max_sentences_per_sku=max_sentences_per_sku,
            llm_mode=LLM_MODE_OFF,
            llm_batch_size=llm_batch_size,
            force_rebuild=True,
            coverage_mode=COMMENT_COVERAGE_REBUILD_ONLY,
        )

    child_warnings = [
        warning
        for item in completed_results
        for warning in (item.get("warnings") or [])
        if warning
    ]
    coverage_status = (
        final_coverage_result.get("status") if final_coverage_result else None
    )
    has_coverage_error = coverage_status == "error"
    status = (
        "error"
        if failed_results or has_coverage_error
        else "warning"
        if child_warnings or skipped_results
        else "ok"
    )
    module_status = (
        "failed"
        if status == "error"
        else "warning"
        if status == "warning"
        else "success"
    )
    summary = {
        "comment_profile_batch": True,
        "batch_id": resolved_batch_id,
        "product_category": product_category,
        "taxonomy_version": config["comment_taxonomy_version"],
        "rule_version": config["comment_rule_version"],
        "parallelism": parallelism,
        "effective_parallelism": min(parallelism, len(scheduled_skus))
        if scheduled_skus
        else 0,
        "limit": limit,
        "rerun_existing": rerun_existing,
        "force_rebuild": force_rebuild,
        "max_sentences_per_sku": max_sentences_per_sku,
        "llm_mode": llm_mode,
        "llm_batch_size": llm_batch_size,
        "candidate_sku_count": len(plan["candidate_sku_codes"]),
        "existing_profile_sku_count": len(plan["existing_profile_sku_codes"]),
        "pending_sku_count_before_limit": len(plan["pending_sku_codes_before_limit"]),
        "scheduled_sku_count": len(scheduled_skus),
        "completed_sku_count": len(completed_results),
        "failed_sku_count": len(failed_results),
        "skipped_sku_count": len(skipped_results),
        "excluded_sku_count": len(plan["excluded_sku_codes"]),
        "ignored_requested_sku_count": len(plan["ignored_requested_sku_codes"]),
        "final_coverage_rebuilt": final_coverage_result is not None,
        "final_coverage_status": coverage_status,
        "final_coverage_summary": final_coverage_result.get("summary")
        if final_coverage_result
        else None,
    }
    return {
        "status": status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "taxonomy_version": config["comment_taxonomy_version"],
        "rule_version": config["comment_rule_version"],
        "module_status": module_status,
        "input_count": len(scheduled_skus),
        "output_count": len(completed_results),
        "warnings": _unique_string_list(child_warnings),
        "summary": summary,
        "candidate_sku_codes": plan["candidate_sku_codes"],
        "pending_sku_codes_before_limit": plan["pending_sku_codes_before_limit"],
        "scheduled_sku_codes": scheduled_skus,
        "excluded_sku_codes": plan["excluded_sku_codes"],
        "ignored_requested_sku_codes": plan["ignored_requested_sku_codes"],
        "sku_results": sku_results,
        "failed_sku_results": failed_results,
        "final_coverage": final_coverage_result,
    }


def run_comment_profile_batch_worker(
    *,
    session_factory: Any,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_code: str,
    taxonomy_version: str,
    rule_version: str,
    max_sentences_per_sku: int,
    llm_mode: str,
    llm_batch_size: int,
    force_rebuild: bool,
    rerun_existing: bool,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    try:
        with session_factory() as worker_db:
            if not rerun_existing and comment_profile_exists(
                worker_db,
                project_id=project_id,
                source_category_code=source_category_code,
                batch_id=batch_id,
                product_category=product_category,
                sku_code=sku_code,
                taxonomy_version=taxonomy_version,
                rule_version=rule_version,
            ):
                return {
                    "sku_code": sku_code,
                    "status": "skipped",
                    "module_status": "skipped_existing_profile",
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            result = run_comment_profile(
                worker_db,
                project_id=project_id,
                source_category_code=source_category_code,
                batch_id=batch_id,
                product_category=product_category,
                sku_scope=(sku_code,),
                max_sentences_per_sku=max_sentences_per_sku,
                llm_mode=llm_mode,
                llm_batch_size=llm_batch_size,
                force_rebuild=force_rebuild,
                coverage_mode=COMMENT_COVERAGE_SKIP,
            )
            return {
                "sku_code": sku_code,
                "status": result.get("status"),
                "module_status": result.get("module_status"),
                "input_count": result.get("input_count"),
                "output_count": result.get("output_count"),
                "changed_input_count": result.get("changed_input_count"),
                "warnings": result.get("warnings") or [],
                "summary": result.get("summary") or {},
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        return {
            "sku_code": sku_code,
            "status": "error",
            "module_status": "failed",
            "error": str(exc),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }


def plan_comment_profile_batch_skus(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_code_prefix: str,
    taxonomy_version: str,
    rule_version: str,
    sku_scope: Sequence[str] = (),
    exclude_sku_scope: Sequence[str] = (),
    rerun_existing: bool = False,
    limit: int | None = None,
) -> dict[str, list[str]]:
    requested_sku_codes = normalize_sku_codes(sku_scope)
    excluded_sku_codes = normalize_sku_codes(exclude_sku_scope)
    stmt = (
        select(entities.Core3EvidenceAtom.sku_code)
        .where(entities.Core3EvidenceAtom.project_id == project_id)
        .where(entities.Core3EvidenceAtom.category_code == source_category_code)
        .where(entities.Core3EvidenceAtom.batch_id == batch_id)
        .where(entities.Core3EvidenceAtom.is_current.is_(True))
        .where(
            entities.Core3EvidenceAtom.evidence_status
            == Core3EvidenceStatus.CURRENT.value
        )
        .where(
            entities.Core3EvidenceAtom.evidence_type
            == Core3EvidenceType.COMMENT_SENTENCE.value
        )
        .where(entities.Core3EvidenceAtom.sku_code.like(f"{sku_code_prefix}%"))
        .distinct()
        .order_by(entities.Core3EvidenceAtom.sku_code)
    )
    if requested_sku_codes:
        stmt = stmt.where(
            entities.Core3EvidenceAtom.sku_code.in_(tuple(requested_sku_codes))
        )
    candidate_sku_codes = [str(row) for row in db.execute(stmt).scalars().all() if row]
    candidate_sku_codes = [
        sku for sku in candidate_sku_codes if sku not in set(excluded_sku_codes)
    ]
    existing_profile_sku_codes = list_existing_comment_profile_skus(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=batch_id,
        product_category=product_category,
        taxonomy_version=taxonomy_version,
        rule_version=rule_version,
        sku_codes=candidate_sku_codes,
    )
    existing_set = set(existing_profile_sku_codes)
    pending_sku_codes = (
        list(candidate_sku_codes)
        if rerun_existing
        else [sku for sku in candidate_sku_codes if sku not in existing_set]
    )
    pending_before_limit = list(pending_sku_codes)
    scheduled_sku_codes = pending_sku_codes[:limit] if limit else pending_sku_codes
    candidate_set = set(candidate_sku_codes)
    ignored_requested_sku_codes = [
        sku
        for sku in requested_sku_codes
        if sku not in candidate_set and sku not in set(excluded_sku_codes)
    ]
    return {
        "candidate_sku_codes": candidate_sku_codes,
        "existing_profile_sku_codes": existing_profile_sku_codes,
        "pending_sku_codes_before_limit": pending_before_limit,
        "scheduled_sku_codes": scheduled_sku_codes,
        "excluded_sku_codes": excluded_sku_codes,
        "ignored_requested_sku_codes": ignored_requested_sku_codes,
    }


def list_existing_comment_profile_skus(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    taxonomy_version: str,
    rule_version: str,
    sku_codes: Sequence[str],
) -> list[str]:
    if not sku_codes:
        return []
    stmt = (
        select(entities.Core3SkuCommentFactProfile.sku_code)
        .where(entities.Core3SkuCommentFactProfile.project_id == project_id)
        .where(
            entities.Core3SkuCommentFactProfile.category_code == source_category_code
        )
        .where(entities.Core3SkuCommentFactProfile.batch_id == batch_id)
        .where(entities.Core3SkuCommentFactProfile.product_category == product_category)
        .where(entities.Core3SkuCommentFactProfile.taxonomy_version == taxonomy_version)
        .where(entities.Core3SkuCommentFactProfile.rule_version == rule_version)
        .where(entities.Core3SkuCommentFactProfile.is_current.is_(True))
        .where(entities.Core3SkuCommentFactProfile.sku_code.in_(tuple(sku_codes)))
        .distinct()
        .order_by(entities.Core3SkuCommentFactProfile.sku_code)
    )
    return [str(row) for row in db.execute(stmt).scalars().all() if row]


def comment_profile_exists(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    sku_code: str,
    taxonomy_version: str,
    rule_version: str,
) -> bool:
    stmt = (
        select(entities.Core3SkuCommentFactProfile.sku_code)
        .where(entities.Core3SkuCommentFactProfile.project_id == project_id)
        .where(
            entities.Core3SkuCommentFactProfile.category_code == source_category_code
        )
        .where(entities.Core3SkuCommentFactProfile.batch_id == batch_id)
        .where(entities.Core3SkuCommentFactProfile.product_category == product_category)
        .where(entities.Core3SkuCommentFactProfile.taxonomy_version == taxonomy_version)
        .where(entities.Core3SkuCommentFactProfile.rule_version == rule_version)
        .where(entities.Core3SkuCommentFactProfile.is_current.is_(True))
        .where(entities.Core3SkuCommentFactProfile.sku_code == sku_code)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def run_market_profile(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str = "TV",
    sku_scope: Sequence[str] = (),
    analysis_windows: Sequence[str] = (),
    sku_chunk_size: int = DEFAULT_M07_SKU_CHUNK_SIZE,
) -> dict[str, Any]:
    if sku_chunk_size <= 0:
        raise CatForgePipelineError("M07 SKU 分批大小必须大于 0。")
    config = product_category_config(product_category)
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    effective_sku_scope = tuple(sku_scope) or tuple(
        list_sku_codes_with_prefix(
            db,
            project_id,
            source_category_code,
            resolved_batch_id,
            str(config["sku_code_prefix"]),
        )
    )
    if not effective_sku_scope:
        raise CatForgePipelineError(
            f"批次 {resolved_batch_id} 没有可用于 M07 市场画像的 {config['sku_code_prefix']} 前缀 SKU。"
        )
    analysis_window_values = resolve_m07_analysis_windows(analysis_windows)
    run_id, module_run_id = ensure_m07_cli_run_records(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=resolved_batch_id,
        sku_scope=effective_sku_scope,
        analysis_windows=analysis_window_values,
        sku_chunk_size=sku_chunk_size,
        product_category=product_category,
    )
    db.commit()
    module_result = run_market_profile_windows(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=resolved_batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        product_category=product_category,
        sku_scope=effective_sku_scope,
        analysis_windows=analysis_window_values,
        sku_chunk_size=sku_chunk_size,
    )
    status_value = enum_value(module_result.status)
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        finish_m07_cli_run_records(
            db, run_id=run_id, module_run_id=module_run_id, module_result=module_result
        )
        db.commit()
    else:
        finish_m07_cli_run_records(
            db, run_id=run_id, module_run_id=module_run_id, module_result=module_result
        )
        db.commit()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "run_id": run_id,
        "module_run_id": module_run_id,
        "sku_scope": list(sku_scope),
        "effective_sku_scope_count": len(effective_sku_scope),
        "sku_scope_mode": "explicit"
        if sku_scope
        else f"{str(config['sku_code_prefix']).lower()}_prefix_default",
        "sku_chunk_size": sku_chunk_size,
        "executed_chunk_count": module_result.summary_json.get("executed_chunk_count")
        if isinstance(module_result.summary_json, dict)
        else None,
        "analysis_windows": list(analysis_windows) or "all",
        "executed_analysis_windows": list(analysis_window_values),
        "rule_version": CORE3_M07_RULE_VERSION,
        "price_band_rule_version": CORE3_M07_PRICE_BAND_RULE_VERSION,
        "pool_rule_version": CORE3_M07_POOL_RULE_VERSION,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_market_profile_windows(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    run_id: str,
    module_run_id: str,
    product_category: str,
    sku_scope: Sequence[str],
    analysis_windows: Sequence[str],
    sku_chunk_size: int,
) -> Any:
    results = []
    executed_chunk_count = 0
    for analysis_window in analysis_windows:
        for sku_chunk in chunk_sequence(sku_scope, sku_chunk_size):
            executed_chunk_count += 1
            module_result = MarketProfileRunner(db).run_batch(
                project_id=project_id,
                category_code=source_category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                product_category=product_category,
                rule_version=CORE3_M07_RULE_VERSION,
                price_band_rule_version=CORE3_M07_PRICE_BAND_RULE_VERSION,
                pool_rule_version=CORE3_M07_POOL_RULE_VERSION,
                sku_scope=sku_chunk,
                analysis_windows=(analysis_window,),
            )
            status_value = enum_value(module_result.status)
            if module_result.status not in {
                Core3RunStatus.SUCCESS,
                Core3RunStatus.WARNING,
            } and status_value not in {"success", "warning"}:
                return module_result
            results.append(module_result)
            db.commit()
            db.expunge_all()
    return aggregate_m07_module_results(
        results,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=batch_id,
        run_id=run_id,
        product_category=product_category,
        sku_scope=sku_scope,
        analysis_windows=analysis_windows,
        sku_chunk_size=sku_chunk_size,
        executed_chunk_count=executed_chunk_count,
    )


def aggregate_m07_module_results(
    results: Sequence[Any],
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    run_id: str,
    product_category: str,
    sku_scope: Sequence[str],
    analysis_windows: Sequence[str],
    sku_chunk_size: int,
    executed_chunk_count: int,
) -> Any:
    if not results:
        return SimpleNamespace(
            module_code=Core3ModuleCode.M07,
            status=Core3RunStatus.BLOCKED,
            input_count=0,
            changed_input_count=0,
            output_count=0,
            output_hash=None,
            warnings=["M07 没有可执行的分析窗口。"],
            review_issues=[],
            downstream_impacts=[],
            summary_json={
                "project_id": project_id,
                "category_code": source_category_code,
                "batch_id": batch_id,
                "run_id": run_id,
                "target_sku_codes": list(sku_scope),
                "analysis_windows": list(analysis_windows),
                "sku_chunk_size": sku_chunk_size,
                "executed_chunk_count": executed_chunk_count,
            },
            started_at=cli_now(),
            finished_at=cli_now(),
        )
    warnings = unique_strings(
        item
        for result in results
        for item in list(getattr(result, "warnings", []) or [])
    )
    review_issues = [
        issue
        for result in results
        for issue in list(getattr(result, "review_issues", []) or [])
    ]
    downstream_impacts = [
        impact
        for result in results
        for impact in list(getattr(result, "downstream_impacts", []) or [])
    ]
    summary_json = aggregate_m07_summary(
        results,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=batch_id,
        run_id=run_id,
        product_category=product_category,
        sku_scope=sku_scope,
        analysis_windows=analysis_windows,
        sku_chunk_size=sku_chunk_size,
        executed_chunk_count=executed_chunk_count,
    )
    return SimpleNamespace(
        module_code=Core3ModuleCode.M07,
        status=Core3RunStatus.WARNING if warnings else Core3RunStatus.SUCCESS,
        input_count=max(
            int(getattr(result, "input_count", 0) or 0) for result in results
        ),
        changed_input_count=sum(
            int(getattr(result, "changed_input_count", 0) or 0) for result in results
        ),
        output_count=sum(
            int(getattr(result, "output_count", 0) or 0) for result in results
        ),
        output_hash=stable_cli_uuid("m07-aggregate-output", summary_json),
        warnings=warnings,
        review_issues=review_issues,
        downstream_impacts=downstream_impacts,
        summary_json=summary_json,
        started_at=min(getattr(result, "started_at", cli_now()) for result in results),
        finished_at=max(
            getattr(result, "finished_at", cli_now()) for result in results
        ),
    )


def aggregate_m07_summary(
    results: Sequence[Any],
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    run_id: str,
    product_category: str,
    sku_scope: Sequence[str],
    analysis_windows: Sequence[str],
    sku_chunk_size: int,
    executed_chunk_count: int,
) -> dict[str, Any]:
    count_keys = (
        "market_profile_count",
        "market_signal_count",
        "comparable_pool_count",
        "pool_member_count",
        "review_required_count",
        "created_output_count",
        "updated_output_count",
        "reused_output_count",
    )
    summary: dict[str, Any] = {
        "project_id": project_id,
        "category_code": source_category_code,
        "product_category": product_category,
        "batch_id": batch_id,
        "run_id": run_id,
        "target_sku_codes": list(sku_scope),
        "analysis_windows": list(analysis_windows),
        "processed_sku_count": len(set(sku_scope)),
        "window_execution_mode": "sequential",
        "sku_execution_mode": "chunked",
        "sku_chunk_size": sku_chunk_size,
        "executed_chunk_count": executed_chunk_count,
        "rule_version": CORE3_M07_RULE_VERSION,
        "price_band_rule_version": CORE3_M07_PRICE_BAND_RULE_VERSION,
        "pool_rule_version": CORE3_M07_POOL_RULE_VERSION,
    }
    for key in count_keys:
        summary[key] = sum(
            int((getattr(result, "summary_json", {}) or {}).get(key) or 0)
            for result in results
        )
    summary["sku_count"] = max(
        int((getattr(result, "summary_json", {}) or {}).get("sku_count") or 0)
        for result in results
    )
    summary["scope_notes"] = unique_strings(
        note
        for result in results
        for note in list(
            (getattr(result, "summary_json", {}) or {}).get("scope_notes") or []
        )
    )
    summary["quality_notes"] = unique_strings(
        note
        for result in results
        for note in list(
            (getattr(result, "summary_json", {}) or {}).get("quality_notes") or []
        )
    )
    summary["sample_status_counts"] = merge_count_dicts(
        (getattr(result, "summary_json", {}) or {}).get("sample_status_counts") or {}
        for result in results
    )
    summary["pool_status_counts"] = merge_count_dicts(
        (getattr(result, "summary_json", {}) or {}).get("pool_status_counts") or {}
        for result in results
    )
    first_summary = getattr(results[0], "summary_json", {}) or {}
    for key in ("boundary_note", "downstream_support"):
        if key in first_summary:
            summary[key] = first_summary[key]
    summary["window_summaries"] = [
        {
            "analysis_windows": list(
                (getattr(result, "summary_json", {}) or {}).get("analysis_windows")
                or []
            ),
            "market_profile_count": (getattr(result, "summary_json", {}) or {}).get(
                "market_profile_count", 0
            ),
            "market_signal_count": (getattr(result, "summary_json", {}) or {}).get(
                "market_signal_count", 0
            ),
            "comparable_pool_count": (getattr(result, "summary_json", {}) or {}).get(
                "comparable_pool_count", 0
            ),
            "pool_member_count": (getattr(result, "summary_json", {}) or {}).get(
                "pool_member_count", 0
            ),
            "review_required_count": (getattr(result, "summary_json", {}) or {}).get(
                "review_required_count", 0
            ),
        }
        for result in results
    ]
    return summary


def resolve_m07_analysis_windows(analysis_windows: Sequence[str]) -> tuple[str, ...]:
    if analysis_windows:
        return tuple(str(window) for window in analysis_windows)
    return tuple(
        window.value if hasattr(window, "value") else str(window)
        for window in M07_ANALYSIS_WINDOWS
    )


def chunk_sequence(values: Sequence[str], chunk_size: int) -> list[tuple[str, ...]]:
    return [
        tuple(values[index : index + chunk_size])
        for index in range(0, len(values), chunk_size)
    ]


def unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def merge_count_dicts(dicts: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for count_dict in dicts:
        for key, value in count_dict.items():
            merged[str(key)] = merged.get(str(key), 0) + int(value or 0)
    return merged


def ensure_m07_cli_run_records(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    sku_scope: Sequence[str],
    analysis_windows: Sequence[str],
    sku_chunk_size: int,
    product_category: str = "TV",
) -> tuple[str, str]:
    run_id = stable_cli_uuid(
        "m07-pipeline-run",
        {
            "project_id": project_id,
            "category_code": source_category_code,
            "product_category": product_category,
            "batch_id": batch_id,
            "sku_scope": sorted(str(sku_code) for sku_code in sku_scope),
            "analysis_windows": list(analysis_windows) or ["all"],
        },
    )
    module_run_id = stable_cli_uuid(
        "m07-module-run", {"run_id": run_id, "module_code": Core3ModuleCode.M07.value}
    )
    now = cli_now()
    pipeline_run = db.get(entities.Core3V2PipelineRun, run_id)
    if pipeline_run is None:
        pipeline_run = entities.Core3V2PipelineRun(
            run_id=run_id,
            project_id=project_id,
            category_code=source_category_code,
            run_mode=Core3RunMode.DAILY_INCREMENTAL.value,
            trigger_type=Core3PipelineTriggerType.MANUAL.value,
            triggered_by="catforge-cli",
            data_batch_id=batch_id,
            ruleset_version=CORE3_DEFAULT_RULESET_VERSION,
        )
        db.add(pipeline_run)
    pipeline_run.status = Core3RunStatus.RUNNING.value
    pipeline_run.release_status = Core3ReleaseGateStatus.NOT_READY.value
    pipeline_run.started_at = now
    pipeline_run.finished_at = None
    pipeline_run.error_code = None
    pipeline_run.error_message_cn = None
    pipeline_run.data_batch_id = batch_id
    pipeline_run.target_scope_json = {
        "scope_type": "cli_market_profile",
        "module_code": Core3ModuleCode.M07.value,
        "product_category": product_category,
        "sku_count": len(sku_scope),
        "sku_scope": list(sku_scope),
        "analysis_windows": list(analysis_windows) or ["all"],
        "sku_chunk_size": sku_chunk_size,
    }
    pipeline_run.module_version_json = {
        Core3ModuleCode.M07.value: CORE3_M07_MODULE_VERSION
    }
    pipeline_run.seed_version_json = {}
    pipeline_run.input_watermark_json = {"batch_id": batch_id}
    pipeline_run.output_summary_json = {}
    pipeline_run.quality_summary_json = {}
    db.flush()

    module_run = db.get(entities.Core3V2ModuleRun, module_run_id)
    if module_run is None:
        module_run = entities.Core3V2ModuleRun(module_run_id=module_run_id)
        db.add(module_run)
    module_run.run_id = run_id
    module_run.project_id = project_id
    module_run.category_code = source_category_code
    module_run.module_code = Core3ModuleCode.M07.value
    module_run.target_scope = "sku_scope"
    module_run.target_id = batch_id
    module_run.batch_id = batch_id
    module_run.status = Core3RunStatus.RUNNING.value
    module_run.input_count = 0
    module_run.changed_input_count = 0
    module_run.output_count = 0
    module_run.output_hash = None
    module_run.warnings_json = []
    module_run.review_issue_summary_json = {"count": 0, "items": []}
    module_run.downstream_impact_json = {"items": []}
    module_run.summary_json = {"note_cn": "CLI 触发 M07 市场画像生成中。"}
    module_run.started_at = now
    module_run.finished_at = None
    module_run.error_code = None
    module_run.error_message_cn = None
    db.flush()
    return run_id, module_run_id


def finish_m07_cli_run_records(
    db: Session, *, run_id: str, module_run_id: str, module_result: Any
) -> None:
    status_value = enum_value(module_result.status)
    finished_at = getattr(module_result, "finished_at", None) or cli_now()
    warnings = list(getattr(module_result, "warnings", []) or [])
    review_issues = list(getattr(module_result, "review_issues", []) or [])
    downstream_impacts = list(getattr(module_result, "downstream_impacts", []) or [])
    summary_json = dict(getattr(module_result, "summary_json", {}) or {})
    issue_items = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        for item in review_issues[:20]
    ]
    issue_summary = {"count": len(review_issues), "items": issue_items}
    error_message_cn = result_error_message_cn(module_result)

    module_run = db.get(entities.Core3V2ModuleRun, module_run_id)
    if module_run is not None:
        module_run.status = status_value
        module_run.input_count = module_result.input_count
        module_run.changed_input_count = module_result.changed_input_count
        module_run.output_count = module_result.output_count
        module_run.output_hash = getattr(module_result, "output_hash", None)
        module_run.warnings_json = warnings
        module_run.review_issue_summary_json = issue_summary
        module_run.downstream_impact_json = {"items": downstream_impacts}
        module_run.summary_json = summary_json
        module_run.started_at = (
            getattr(module_result, "started_at", None) or module_run.started_at
        )
        module_run.finished_at = finished_at
        module_run.error_code = (
            "m07_market_profile_failed"
            if status_value == Core3RunStatus.FAILED.value
            else None
        )
        module_run.error_message_cn = error_message_cn

    pipeline_run = db.get(entities.Core3V2PipelineRun, run_id)
    if pipeline_run is not None:
        pipeline_run.status = status_value
        pipeline_run.finished_at = finished_at
        pipeline_run.output_summary_json = {
            "module_code": Core3ModuleCode.M07.value,
            "input_count": module_result.input_count,
            "changed_input_count": module_result.changed_input_count,
            "output_count": module_result.output_count,
            "warnings": warnings,
            "review_issue_count": len(review_issues),
            "summary": summary_json,
        }
        pipeline_run.quality_summary_json = {
            "warning_count": len(warnings),
            "review_issue_count": len(review_issues),
            "status": status_value,
        }
        pipeline_run.release_status = (
            Core3ReleaseGateStatus.BLOCKED.value
            if status_value
            in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value}
            else Core3ReleaseGateStatus.NOT_READY.value
        )
        pipeline_run.error_code = (
            "m07_market_profile_failed"
            if status_value == Core3RunStatus.FAILED.value
            else None
        )
        pipeline_run.error_message_cn = error_message_cn
    db.flush()


def stable_cli_uuid(kind: str, payload: Any) -> str:
    key = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"catforge:{kind}:{key}"))


def cli_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def result_error_message_cn(module_result: Any) -> str | None:
    status_value = enum_value(module_result.status)
    if status_value not in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value}:
        return None
    warnings = list(getattr(module_result, "warnings", []) or [])
    return "；".join(warnings[:3]) if warnings else "M07 市场画像生成未完成。"


def list_sku_codes_with_prefix(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_prefix: str,
) -> list[str]:
    pattern = f"{sku_prefix}%"
    sku_codes = list(
        db.execute(
            select(entities.Core3CleanSku.sku_code)
            .where(entities.Core3CleanSku.project_id == project_id)
            .where(entities.Core3CleanSku.category_code == category_code)
            .where(entities.Core3CleanSku.batch_id == batch_id)
            .where(entities.Core3CleanSku.sku_code.like(pattern))
            .order_by(entities.Core3CleanSku.sku_code)
        ).scalars()
    )
    if sku_codes:
        return [str(code) for code in sku_codes]
    return [
        str(code)
        for code in db.execute(
            select(entities.Core3CleanMarketWeekly.sku_code)
            .where(entities.Core3CleanMarketWeekly.project_id == project_id)
            .where(entities.Core3CleanMarketWeekly.category_code == category_code)
            .where(entities.Core3CleanMarketWeekly.batch_id == batch_id)
            .where(entities.Core3CleanMarketWeekly.sku_code.like(pattern))
            .distinct()
            .order_by(entities.Core3CleanMarketWeekly.sku_code)
        ).scalars()
    ]


def run_claim_profile(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    input_source: str,
    force_rebuild: bool,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    if not config.get("claim_taxonomy_version") or not config.get("claim_rule_version"):
        raise CatForgePipelineError(
            f"{config['label_cn']}标准卖点 taxonomy 尚未发布，不能生成 SKU 卖点事实画像。"
        )
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M04CRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        product_category=product_category,
        taxonomy_version=config["claim_taxonomy_version"],
        rule_version=config["claim_rule_version"],
        input_source=input_source,
        force_rebuild=force_rebuild,
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "taxonomy_version": config["claim_taxonomy_version"],
        "rule_version": config["claim_rule_version"],
        "input_source": input_source,
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def run_param_profile(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    product_category: str,
    force_rebuild: bool,
) -> dict[str, Any]:
    config = product_category_config(product_category)
    resolved_batch_id = resolve_source_batch_id(
        db, project_id, source_category_code, batch_id
    )
    module_result = M03BRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        taxonomy_version=config["taxonomy_version"],
        parser_version=config["parser_version"],
        rule_version=config["rule_version"],
        force_rebuild=force_rebuild,
        sku_code_prefix=config["sku_code_prefix"],
    )
    status_value = (
        module_result.status.value
        if hasattr(module_result.status, "value")
        else str(module_result.status)
    )
    if module_result.status in {
        Core3RunStatus.SUCCESS,
        Core3RunStatus.WARNING,
    } or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = (
        "ok"
        if status_value == "success"
        else "warning"
        if status_value == "warning"
        else "error"
    )
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": product_category,
        "product_category_label_cn": config["label_cn"],
        "batch_id": resolved_batch_id,
        "sku_code_prefix": config["sku_code_prefix"],
        "taxonomy_version": config["taxonomy_version"],
        "parser_version": config["parser_version"],
        "rule_version": config["rule_version"],
        "force_rebuild": force_rebuild,
        "module_status": status_value,
        "input_count": module_result.input_count,
        "output_count": module_result.output_count,
        "changed_input_count": module_result.changed_input_count,
        "warnings": module_result.warnings,
        "summary": module_result.summary_json,
    }


def resolve_source_batch_id(
    db: Session, project_id: str, source_category_code: str, batch_id: str
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    resolved = db.execute(
        select(entities.Core3SourceBatch.batch_id)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.category_code == source_category_code)
        .order_by(
            entities.Core3SourceBatch.created_at.desc(),
            entities.Core3SourceBatch.batch_id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if not resolved:
        raise CatForgePipelineError(
            f"没有找到项目 {project_id} / {source_category_code} 的可用 source batch。"
        )
    return str(resolved)


def should_run_param_profile(question: str) -> bool:
    return any(
        word in question
        for word in (
            "参数画像",
            "参数事实",
            "标准参数",
            "生成",
            "重跑",
            "重新",
            "更新",
            "数据准备",
            "准备好可以分析",
        )
    )


def should_run_semantic_market_graph(question: str) -> bool:
    normalized = normalize_token(question)
    if "m11d" in normalized or "semanticmarket" in normalized:
        return True
    graph_terms = (
        "语义市场图谱",
        "市场图谱",
        "销量分配",
        "销量切分",
        "销额分配",
        "销额切分",
        "市场空间",
    )
    dimension_graph_terms = (
        "用户任务图谱",
        "目标客群图谱",
        "目标客户图谱",
        "目标用户图谱",
        "价值战场市场图谱",
        "战场市场图谱",
    )
    if any(term in question for term in graph_terms + dimension_graph_terms):
        return any(
            word in normalized
            for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算", "准备")
        )
    return False


def should_run_claim_value_quantification(question: str) -> bool:
    normalized = normalize_token(question)
    if "m12c" in normalized:
        return True
    if not any(
        term in question
        for term in (
            "卖点价值量化",
            "卖点商业价值",
            "卖点贡献归因",
            "卖点价值",
            "卖点贡献",
            "溢价卖点量化",
        )
    ):
        return False
    return any(
        word in normalized
        for word in (
            "生成",
            "重跑",
            "重新",
            "更新",
            "执行",
            "跑",
            "计算",
            "量化",
            "归因",
            "准备好可以分析",
        )
    )


def extract_semantic_dimension_types(question: str) -> tuple[str, ...]:
    result: list[str] = []
    if "用户任务" in question or "任务图谱" in question:
        result.append("user_task")
    if any(
        term in question
        for term in ("目标客群", "目标客户", "目标用户", "客群图谱", "客户图谱")
    ):
        result.append("target_group")
    if "价值战场" in question or "战场图谱" in question or "战场市场" in question:
        result.append("battlefield")
    return tuple(dict.fromkeys(result))


def should_run_value_battlefield(question: str) -> bool:
    normalized = normalize_token(question)
    if (
        "价值战场" not in question
        and "战场图谱" not in question
        and "battlefield" not in normalized
    ):
        return False
    return any(
        word in normalized
        for word in (
            "生成",
            "重跑",
            "重新",
            "更新",
            "执行",
            "跑",
            "计算",
            "准备好可以分析",
            "图谱",
            "画像",
        )
    )


def should_run_target_group(question: str) -> bool:
    normalized = normalize_token(question)
    if (
        not any(
            word in question
            for word in (
                "目标客群",
                "目标客户",
                "目标用户",
                "客群画像",
                "客户画像",
                "人群画像",
            )
        )
        and "targetgroup" not in normalized
    ):
        return False
    return any(
        word in normalized
        for word in (
            "生成",
            "重跑",
            "重新",
            "更新",
            "执行",
            "跑",
            "计算",
            "准备好可以分析",
            "画像",
            "分析",
        )
    )


def should_run_user_task(question: str) -> bool:
    normalized = normalize_token(question)
    if (
        not any(
            word in question
            for word in (
                "用户任务",
                "使用任务",
                "主任务",
                "任务画像",
                "购买目的",
                "使用目的",
            )
        )
        and "usertask" not in normalized
    ):
        return False
    return any(
        word in normalized
        for word in (
            "生成",
            "重跑",
            "重新",
            "更新",
            "执行",
            "跑",
            "计算",
            "准备好可以分析",
            "画像",
            "分析",
        )
    )


def should_run_market_profile(question: str) -> bool:
    normalized = normalize_token(question)
    if "市场画像" in question:
        return any(
            word in normalized
            for word in (
                "生成",
                "重跑",
                "重新",
                "更新",
                "执行",
                "跑",
                "计算",
                "量价",
                "市场画像",
            )
        )
    return any(
        word in normalized for word in ("量价画像", "市场量价", "价格区间", "尺寸区间")
    ) and any(
        word in normalized
        for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算")
    )


def should_run_comment_profile(question: str) -> bool:
    normalized = normalize_token(question)
    if any(
        word in question
        for word in ("评论事实画像", "评论画像", "用户评价画像", "评价事实画像")
    ):
        return any(
            word in normalized
            for word in (
                "生成",
                "重跑",
                "重新",
                "更新",
                "执行",
                "跑",
                "计算",
                "准备好可以分析",
            )
        )
    return any(word in question for word in ("评论", "评价", "品牌力")) and any(
        word in normalized
        for word in (
            "生成",
            "重跑",
            "重新",
            "更新",
            "评论事实",
            "评论画像",
            "用户评价",
            "品牌力",
            "准备好可以分析",
        )
    )


def should_run_comment_profile_batch(question: str) -> bool:
    normalized = normalize_token(question)
    if not should_run_comment_profile(question):
        return False
    return any(
        token in question
        for token in (
            "并行",
            "加速",
            "批量",
            "继续跑完",
            "跑完",
            "剩余",
            "未完成",
            "全量",
        )
    ) or any(
        token in normalized for token in ("parallel", "batch", "continue", "resume")
    )


def should_continue_unscoped_comment_batch(question: str) -> bool:
    normalized = normalize_token(question)
    return any(
        token in question for token in ("继续", "续跑", "跑完", "剩余", "未完成")
    ) or any(token in normalized for token in ("continue", "resume"))


def should_run_claim_profile(question: str) -> bool:
    normalized = normalize_token(question)
    return "卖点" in question and any(
        word in normalized
        for word in (
            "生成",
            "重跑",
            "重新",
            "更新",
            "卖点画像",
            "卖点事实",
            "claimprofile",
            "claimfact",
            "准备好可以分析",
        )
    )


def extract_sku_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\b[A-Z]{1,4}\d{4,}\b", question.upper())))


def normalize_sku_codes(values: Sequence[str]) -> list[str]:
    return sorted(
        {str(value).strip().upper() for value in values if str(value).strip()}
    )


def _unique_string_list(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def extract_battlefield_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\bBF_[A-Z0-9_]+\b", question.upper())))


def extract_target_group_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\bTG_[A-Z0-9_]+\b", question.upper())))


def extract_user_task_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\bTASK_[A-Z0-9_]+\b", question.upper())))


def extract_analysis_windows(question: str) -> list[str]:
    normalized = normalize_token(question)
    windows: list[str] = []
    if any(
        token in normalized
        for token in ("全量", "全观察", "完整窗口", "fullobservedwindow")
    ):
        windows.append("full_observed_window")
    if any(token in normalized for token in ("最新周", "latestweek")):
        windows.append("latest_week")
    if any(token in normalized for token in ("近4周", "最近4周", "recent4w")):
        windows.append("recent_4w")
    if any(token in normalized for token in ("近8周", "最近8周", "recent8w")):
        windows.append("recent_8w")
    if any(token in normalized for token in ("近12周", "最近12周", "recent12w")):
        windows.append("recent_12w")
    return windows


def normalize_product_category_arg(value: str | None) -> str:
    normalized = normalize_token(value or "TV")
    if normalized in {"tv", "彩电", "电视"}:
        return "TV"
    if normalized in {"ac", "空调"}:
        return "AC"
    raise CatForgePipelineError(f"不支持的产品品类：{value}")


def resolve_product_category(value: str | None, *, question: str) -> str:
    normalized = normalize_token(value or "auto")
    if normalized != "auto":
        return normalize_product_category_arg(value)
    question_norm = normalize_token(question)
    if "空调" in question_norm or re.search(r"\bAC\d{4,}\b", question.upper()):
        return "AC"
    return "TV"


def product_category_config(product_category: str) -> dict[str, Any]:
    return PRODUCT_CATEGORY_CONFIGS[normalize_product_category_arg(product_category)]


def normalize_token(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def emit_result(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(
            json.dumps(
                to_jsonable(result), ensure_ascii=False, indent=2, sort_keys=True
            )
        )
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
    if result.get("status") not in {"ok", "warning"}:
        return result.get("error") or json.dumps(
            to_jsonable(result), ensure_ascii=False
        )
    label = result.get("product_category_label_cn") or result.get("product_category")
    summary = result.get("summary") or {}
    is_claim_profile = isinstance(summary, dict) and "claim_fact_count" in summary
    is_comment_profile = isinstance(summary, dict) and "comment_fact_count" in summary
    is_comment_batch = isinstance(summary, dict) and bool(
        summary.get("comment_profile_batch")
    )
    is_market_profile = isinstance(summary, dict) and "market_profile_count" in summary
    is_claim_value_quantification = (
        isinstance(summary, dict) and "sku_claim_value_count" in summary
    )
    is_target_group_profile = (
        isinstance(summary, dict) and "target_group_count" in summary
    )
    is_value_battlefield_profile = (
        isinstance(summary, dict) and "battlefield_count" in summary
    )
    if is_comment_batch:
        job_name = "SKU 评论事实画像批量并行"
        input_label = "调度 SKU"
    elif is_claim_value_quantification:
        job_name = "卖点价值量化与商业价值分析"
        input_label = "输入 SKU"
    elif is_market_profile:
        job_name = "SKU 市场画像"
        input_label = "输入周销量价"
    elif is_target_group_profile:
        job_name = "SKU 目标客群画像"
        input_label = "输入 SKU"
    elif is_value_battlefield_profile:
        job_name = "SKU 价值战场画像"
        input_label = "输入 SKU"
    elif is_comment_profile:
        job_name = "SKU 评论事实画像"
        input_label = "输入评论句子"
    elif is_claim_profile:
        job_name = "SKU 卖点事实画像"
        input_label = "输入卖点"
    else:
        job_name = "SKU 参数画像"
        input_label = "输入 evidence"
    lines = [
        f"{label} {job_name}生成完成：status={result['module_status']}",
        f"批次：{result['batch_id']}；{input_label}：{result['input_count']}；输出：{result['output_count']}",
    ]
    if result.get("sku_code_prefix"):
        lines[-1] += f"；前缀：{result['sku_code_prefix']}"
    if result.get("taxonomy_version"):
        lines.append(
            f"taxonomy={result['taxonomy_version']}；rule={result['rule_version']}"
        )
    else:
        lines.append(f"rule={result['rule_version']}")
    if result.get("warnings"):
        lines.append("warnings: " + ", ".join(result["warnings"]))
    if isinstance(summary, dict):
        if is_comment_batch:
            lines.append(
                "SKU："
                f"候选 {summary.get('candidate_sku_count', 0)}；已有 {summary.get('existing_profile_sku_count', 0)}；"
                f"待跑 {summary.get('pending_sku_count_before_limit', 0)}；本次调度 {summary.get('scheduled_sku_count', 0)}；"
                f"完成 {summary.get('completed_sku_count', 0)}；失败 {summary.get('failed_sku_count', 0)}；"
                f"worker={summary.get('effective_parallelism', 0)}/{summary.get('parallelism', 0)}"
            )
            lines.append(
                "coverage："
                f"rebuilt={summary.get('final_coverage_rebuilt')}；status={summary.get('final_coverage_status') or '-'}"
            )
        elif is_market_profile:
            lines.append(
                "画像数："
                f"{summary.get('market_profile_count', 0)}；市场信号：{summary.get('market_signal_count', 0)}；"
                f"可比池：{summary.get('comparable_pool_count', 0)}；池成员：{summary.get('pool_member_count', 0)}；"
                f"需复核：{summary.get('review_required_count', 0)}"
            )
        elif is_claim_value_quantification:
            lines.append(
                "量化结果："
                f"可比池 {summary.get('claim_pool_count', 0)}；池指标 {summary.get('pool_metric_count', 0)}；"
                f"SKU×卖点 {summary.get('sku_claim_value_count', 0)}；SKU 归因 {summary.get('sku_attribution_count', 0)}；"
                f"维度汇总 {summary.get('dimension_summary_count', 0)}；需复核 {summary.get('review_issue_count', 0)}"
            )
            lines.append(
                f"角色分布：{json.dumps(summary.get('role_counts') or {}, ensure_ascii=False, sort_keys=True)}"
            )
        elif is_comment_profile:
            llm_stats = summary.get("llm_stats") or {}
            lines.append(
                "画像数："
                f"{summary.get('sku_profile_count', 0)}；评论事实：{summary.get('comment_fact_count', 0)}；"
                f"覆盖：{summary.get('comment_coverage_count', 0)}；服务排除句：{summary.get('service_excluded_sentence_count', 0)}；"
                f"需复核：{summary.get('review_issue_count', 0)}"
            )
            lines.append(
                "LLM："
                f"mode={llm_stats.get('llm_mode', result.get('llm_mode'))}；called={llm_stats.get('llm_called')}；"
                f"model={llm_stats.get('llm_model', '-')}"
            )
        elif is_target_group_profile:
            lines.append(
                "画像数："
                f"{summary.get('profile_count', 0)}；客群分数：{summary.get('score_count', 0)}；"
                f"覆盖：{summary.get('coverage_count', 0)}；客群数：{summary.get('target_group_count', 0)}"
            )
            lines.append(
                f"主客群分布：{json.dumps(summary.get('primary_target_group_counts', {}), ensure_ascii=False, sort_keys=True)}"
            )
        elif is_value_battlefield_profile:
            lines.append(
                "画像数："
                f"{summary.get('profile_count', 0)}；战场分数：{summary.get('score_count', 0)}；"
                f"图谱：{summary.get('graph_snapshot_count', 0)}；战场数：{summary.get('battlefield_count', 0)}"
            )
            lines.append(
                f"主战场分布：{json.dumps(summary.get('primary_battlefield_counts', {}), ensure_ascii=False, sort_keys=True)}"
            )
        elif is_claim_profile:
            lines.append(
                "画像数："
                f"{summary.get('sku_profile_count', 0)}；卖点事实：{summary.get('claim_fact_count', 0)}；"
                f"事实卖点：{summary.get('fact_claim_count', 0)}；位置：{summary.get('dimension_position_count', 0)}；"
                f"覆盖：{summary.get('position_coverage_count', 0)}"
            )
        else:
            lines.append(
                "画像数："
                f"{summary.get('sku_profile_count', 0)}；参数值：{summary.get('param_value_count', 0)}；"
                f"档位：{summary.get('dimension_tier_count', 0)}；覆盖：{summary.get('tier_coverage_count', 0)}"
            )
    return "\n".join(lines)


class CatForgePipelineError(Exception):
    """User-facing CLI error."""


if __name__ == "__main__":
    sys.exit(main())
