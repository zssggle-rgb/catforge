"""Execution CLI for CatForge data-preparation and fact-profile jobs.

This module is intentionally small and agent-friendly. It exposes write actions
that natural-language agents can call without asking users to know module codes.
"""

from __future__ import annotations

import argparse
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
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_MODULE_VERSION,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    Core3ModuleCode,
    Core3PipelineTriggerType,
    Core3ReleaseGateStatus,
    Core3RunMode,
    Core3RunStatus,
    M07_ANALYSIS_WINDOWS,
)
from app.services.core3_real_data.m03b_param_profile_service import M03BRunner
from app.services.core3_real_data.m04c_claim_fact_profile_service import INPUT_SOURCE_AUTO, M04CRunner
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


DEFAULT_PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_CATEGORY_CODE = "TV"
LATEST_BATCH = "latest"
DEFAULT_M07_SKU_CHUNK_SIZE = 50
COMMENT_COVERAGE_AUTO = "auto"
COMMENT_COVERAGE_INLINE = "inline"
COMMENT_COVERAGE_SKIP = "skip"
COMMENT_COVERAGE_REBUILD_ONLY = "rebuild-only"

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
    },
    "AC": {
        "label_cn": "空调",
        "sku_code_prefix": "AC",
        "taxonomy_version": CORE3_M03B_AC_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_AC_PARSER_VERSION,
        "rule_version": CORE3_M03B_AC_RULE_VERSION,
        "claim_taxonomy_version": None,
        "claim_rule_version": None,
        "comment_taxonomy_version": None,
        "comment_rule_version": None,
        "user_task_taxonomy_version": None,
        "user_task_rule_version": None,
        "target_group_taxonomy_version": None,
        "target_group_rule_version": None,
        "value_battlefield_taxonomy_version": None,
        "value_battlefield_rule_version": None,
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
                    product_category=normalize_product_category_arg(args.product_category),
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-claim-profile":
                result = run_claim_profile(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(args.product_category),
                    input_source=args.input_source,
                    force_rebuild=args.force_rebuild,
                )
            elif args.command == "run-market-profile":
                result = run_market_profile(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
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
                    product_category=normalize_product_category_arg(args.product_category),
                    sku_scope=args.sku_code or (),
                    max_sentences_per_sku=args.max_sentences_per_sku,
                    llm_mode=args.llm_mode,
                    llm_batch_size=args.llm_batch_size,
                    force_rebuild=args.force_rebuild,
                    coverage_mode=args.coverage_mode,
                )
            elif args.command == "run-user-task":
                result = run_user_task(
                    db,
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=normalize_product_category_arg(args.product_category),
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
                    product_category=normalize_product_category_arg(args.product_category),
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
                    product_category=normalize_product_category_arg(args.product_category),
                    sku_scope=args.sku_code or (),
                    battlefield_codes=args.battlefield_code or (),
                    graph_mode=args.graph_mode,
                    force_rebuild=args.force_rebuild,
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

    run_profile = subparsers.add_parser("run-param-profile", help="Generate or rerun SKU parameter fact profiles for a product category.")
    add_common_args(run_profile)
    add_product_category_arg(run_profile, default="tv", allow_auto=False)
    run_profile.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_profile)

    run_claim = subparsers.add_parser("run-claim-profile", help="Generate or rerun SKU claim fact profiles for a product category.")
    add_common_args(run_claim)
    add_product_category_arg(run_claim, default="tv", allow_auto=False)
    run_claim.add_argument("--input-source", choices=("auto", "evidence", "clean", "raw"), default=INPUT_SOURCE_AUTO, help="Claim input source. auto prefers M02 evidence, then M01 clean claims, then raw selling_points_data.")
    run_claim.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_claim)

    run_comment = subparsers.add_parser("run-comment-profile", help="Generate or rerun SKU comment fact profiles for a product category.")
    add_common_args(run_comment)
    add_product_category_arg(run_comment, default="tv", allow_auto=False)
    run_comment.add_argument("--sku-code", action="append", help="Optional SKU scope. Repeat to run selected SKUs only.")
    run_comment.add_argument("--max-sentences-per-sku", type=int, default=500, help="Maximum M02 comment sentences read per SKU to keep memory bounded.")
    run_comment.add_argument("--llm-mode", choices=(LLM_MODE_AUTO, LLM_MODE_REQUIRED, LLM_MODE_OFF), default=LLM_MODE_AUTO, help="LLM usage for comment semantic extraction. Use required on 205 validation to ensure the model is called.")
    run_comment.add_argument("--llm-batch-size", type=int, default=M05C_DEFAULT_LLM_BATCH_SIZE, help="Number of comment sentences per LLM request.")
    run_comment.add_argument(
        "--coverage-mode",
        choices=(COMMENT_COVERAGE_AUTO, COMMENT_COVERAGE_INLINE, COMMENT_COVERAGE_SKIP, COMMENT_COVERAGE_REBUILD_ONLY),
        default=COMMENT_COVERAGE_AUTO,
        help="Comment coverage handling. auto skips coverage for SKU-scoped runs; rebuild-only recomputes batch coverage from saved comment facts.",
    )
    run_comment.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_comment)

    run_market = subparsers.add_parser("run-market-profile", help="Generate or rerun SKU market profiles and comparable-pool baselines.")
    add_common_args(run_market)
    run_market.add_argument("--analysis-window", action="append", choices=("full_observed_window", "latest_week", "recent_4w", "recent_8w", "recent_12w"), help="Analysis window to run. Repeat for multiple windows. Default runs all M07 windows.")
    run_market.add_argument("--sku-code", action="append", help="Optional SKU scope. Repeat to run selected SKUs only.")
    run_market.add_argument("--sku-chunk-size", type=int, default=DEFAULT_M07_SKU_CHUNK_SIZE, help="Number of SKUs per M07 execution chunk. Default keeps 205 memory below the API container limit.")
    add_format_arg(run_market)

    run_value_battlefield = subparsers.add_parser("run-value-battlefield", help="Generate or rerun SKU value battlefield profiles and graph snapshots.")
    add_common_args(run_value_battlefield)
    add_product_category_arg(run_value_battlefield, default="tv", allow_auto=False)
    run_value_battlefield.add_argument("--sku-code", action="append", help="Optional SKU scope. Repeat to run selected SKUs only.")
    run_value_battlefield.add_argument("--battlefield-code", action="append", help="Optional battlefield scope. Repeat to run selected battlefields only.")
    run_value_battlefield.add_argument("--graph-mode", choices=("inline", "skip", "rebuild-only"), default="inline", help="Graph handling. inline rebuilds graph with SKU profiles; skip writes only SKU profiles/scores; rebuild-only writes graph for the selected scope.")
    run_value_battlefield.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_value_battlefield)

    run_user_task = subparsers.add_parser("run-user-task", help="Generate or rerun SKU user-task profiles and coverage.")
    add_common_args(run_user_task)
    add_product_category_arg(run_user_task, default="tv", allow_auto=False)
    run_user_task.add_argument("--sku-code", action="append", help="Optional SKU scope. Repeat to run selected SKUs only.")
    run_user_task.add_argument("--user-task-code", action="append", help="Optional user-task scope. Repeat to run selected user tasks only.")
    run_user_task.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_user_task)

    run_target_group = subparsers.add_parser("run-target-group", help="Generate or rerun SKU target-group profiles and coverage.")
    add_common_args(run_target_group)
    add_product_category_arg(run_target_group, default="tv", allow_auto=False)
    run_target_group.add_argument("--sku-code", action="append", help="Optional SKU scope. Repeat to run selected SKUs only.")
    run_target_group.add_argument("--target-group-code", action="append", help="Optional target-group scope. Repeat to run selected target groups only.")
    run_target_group.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_target_group)

    ask = subparsers.add_parser("ask", help="Route a natural-language execution request.")
    add_common_args(ask)
    add_product_category_arg(ask)
    ask.add_argument("question", nargs="+", help="Natural-language execution request.")
    ask.add_argument("--input-source", choices=("auto", "evidence", "clean", "raw"), default=INPUT_SOURCE_AUTO, help="Claim input source when the natural-language request routes to claim profile generation.")
    ask.add_argument("--max-sentences-per-sku", type=int, default=500, help="Maximum M02 comment sentences read per SKU when routed to comment fact generation.")
    ask.add_argument("--llm-mode", choices=(LLM_MODE_AUTO, LLM_MODE_REQUIRED, LLM_MODE_OFF), default=LLM_MODE_AUTO, help="LLM usage when routed to comment fact generation.")
    ask.add_argument("--llm-batch-size", type=int, default=M05C_DEFAULT_LLM_BATCH_SIZE, help="Comment sentences per LLM request when routed to comment fact generation.")
    ask.add_argument(
        "--coverage-mode",
        choices=(COMMENT_COVERAGE_AUTO, COMMENT_COVERAGE_INLINE, COMMENT_COVERAGE_SKIP, COMMENT_COVERAGE_REBUILD_ONLY),
        default=COMMENT_COVERAGE_AUTO,
        help="Comment coverage handling when routed to comment fact generation.",
    )
    ask.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(ask)
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE, help="Current source-batch category code. The 205 mixed TV/AC batch uses TV.")
    parser.add_argument("--batch-id", default=LATEST_BATCH)


def add_product_category_arg(parser: argparse.ArgumentParser, *, default: str = "auto", allow_auto: bool = True) -> None:
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
) -> dict[str, Any]:
    resolved_product_category = resolve_product_category(product_category, question=question)
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
        result = run_comment_profile(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
            product_category=resolved_product_category,
            sku_scope=extract_sku_scope(question),
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
        if resolved_product_category != "TV":
            raise CatForgePipelineError("M07 市场画像 CLI 当前只支持彩电/TV；其他品类需要先完成对应市场尺寸轴和规则。")
        result = run_market_profile(
            db,
            project_id=project_id,
            source_category_code=source_category_code,
            batch_id=batch_id,
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
        raise CatForgePipelineError("当前执行 CLI 只支持生成/重跑 SKU 参数画像、卖点事实画像、评论事实画像、市场画像、用户任务画像、目标客群画像或价值战场画像。请说明要生成或重新生成哪类画像。")
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
    if not config.get("user_task_taxonomy_version") or not config.get("user_task_rule_version"):
        raise CatForgePipelineError(f"{config['label_cn']}用户任务 taxonomy 尚未发布，不能生成 SKU 用户任务画像。")
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
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
    status_value = module_result.status.value if hasattr(module_result.status, "value") else str(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
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
    if not config.get("target_group_taxonomy_version") or not config.get("target_group_rule_version"):
        raise CatForgePipelineError(f"{config['label_cn']}目标客群 taxonomy 尚未发布，不能生成 SKU 目标客群画像。")
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
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
    status_value = module_result.status.value if hasattr(module_result.status, "value") else str(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
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
    if not config.get("value_battlefield_taxonomy_version") or not config.get("value_battlefield_rule_version"):
        raise CatForgePipelineError(f"{config['label_cn']}价值战场 taxonomy 尚未发布，不能生成 SKU 价值战场画像。")
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
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
    status_value = module_result.status.value if hasattr(module_result.status, "value") else str(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
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
    if not config.get("comment_taxonomy_version") or not config.get("comment_rule_version"):
        raise CatForgePipelineError(f"{config['label_cn']}评论事实 taxonomy 尚未发布，不能生成 SKU 评论事实画像。")
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
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
    status_value = module_result.status.value if hasattr(module_result.status, "value") else str(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
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


def run_market_profile(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    sku_scope: Sequence[str] = (),
    analysis_windows: Sequence[str] = (),
    sku_chunk_size: int = DEFAULT_M07_SKU_CHUNK_SIZE,
) -> dict[str, Any]:
    if sku_chunk_size <= 0:
        raise CatForgePipelineError("M07 SKU 分批大小必须大于 0。")
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
    effective_sku_scope = tuple(sku_scope) or tuple(list_sku_codes_with_prefix(db, project_id, source_category_code, resolved_batch_id, "TV"))
    if not effective_sku_scope:
        raise CatForgePipelineError(f"批次 {resolved_batch_id} 没有可用于 M07 市场画像的 TV 前缀 SKU。")
    analysis_window_values = resolve_m07_analysis_windows(analysis_windows)
    run_id, module_run_id = ensure_m07_cli_run_records(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=resolved_batch_id,
        sku_scope=effective_sku_scope,
        analysis_windows=analysis_window_values,
        sku_chunk_size=sku_chunk_size,
    )
    db.commit()
    module_result = run_market_profile_windows(
        db,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=resolved_batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        sku_scope=effective_sku_scope,
        analysis_windows=analysis_window_values,
        sku_chunk_size=sku_chunk_size,
    )
    status_value = enum_value(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        finish_m07_cli_run_records(db, run_id=run_id, module_run_id=module_run_id, module_result=module_result)
        db.commit()
    else:
        finish_m07_cli_run_records(db, run_id=run_id, module_run_id=module_run_id, module_result=module_result)
        db.commit()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
    return {
        "status": result_status,
        "project_id": project_id,
        "source_category_code": source_category_code,
        "product_category": "TV",
        "product_category_label_cn": "彩电",
        "batch_id": resolved_batch_id,
        "run_id": run_id,
        "module_run_id": module_run_id,
        "sku_scope": list(sku_scope),
        "effective_sku_scope_count": len(effective_sku_scope),
        "sku_scope_mode": "explicit" if sku_scope else "tv_prefix_default",
        "sku_chunk_size": sku_chunk_size,
        "executed_chunk_count": module_result.summary_json.get("executed_chunk_count") if isinstance(module_result.summary_json, dict) else None,
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
                rule_version=CORE3_M07_RULE_VERSION,
                price_band_rule_version=CORE3_M07_PRICE_BAND_RULE_VERSION,
                pool_rule_version=CORE3_M07_POOL_RULE_VERSION,
                sku_scope=sku_chunk,
                analysis_windows=(analysis_window,),
            )
            status_value = enum_value(module_result.status)
            if module_result.status not in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} and status_value not in {"success", "warning"}:
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
    warnings = unique_strings(item for result in results for item in list(getattr(result, "warnings", []) or []))
    review_issues = [issue for result in results for issue in list(getattr(result, "review_issues", []) or [])]
    downstream_impacts = [impact for result in results for impact in list(getattr(result, "downstream_impacts", []) or [])]
    summary_json = aggregate_m07_summary(
        results,
        project_id=project_id,
        source_category_code=source_category_code,
        batch_id=batch_id,
        run_id=run_id,
        sku_scope=sku_scope,
        analysis_windows=analysis_windows,
        sku_chunk_size=sku_chunk_size,
        executed_chunk_count=executed_chunk_count,
    )
    return SimpleNamespace(
        module_code=Core3ModuleCode.M07,
        status=Core3RunStatus.WARNING if warnings else Core3RunStatus.SUCCESS,
        input_count=max(int(getattr(result, "input_count", 0) or 0) for result in results),
        changed_input_count=sum(int(getattr(result, "changed_input_count", 0) or 0) for result in results),
        output_count=sum(int(getattr(result, "output_count", 0) or 0) for result in results),
        output_hash=stable_cli_uuid("m07-aggregate-output", summary_json),
        warnings=warnings,
        review_issues=review_issues,
        downstream_impacts=downstream_impacts,
        summary_json=summary_json,
        started_at=min(getattr(result, "started_at", cli_now()) for result in results),
        finished_at=max(getattr(result, "finished_at", cli_now()) for result in results),
    )


def aggregate_m07_summary(
    results: Sequence[Any],
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    run_id: str,
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
        summary[key] = sum(int((getattr(result, "summary_json", {}) or {}).get(key) or 0) for result in results)
    summary["sku_count"] = max(int((getattr(result, "summary_json", {}) or {}).get("sku_count") or 0) for result in results)
    summary["scope_notes"] = unique_strings(
        note
        for result in results
        for note in list((getattr(result, "summary_json", {}) or {}).get("scope_notes") or [])
    )
    summary["quality_notes"] = unique_strings(
        note
        for result in results
        for note in list((getattr(result, "summary_json", {}) or {}).get("quality_notes") or [])
    )
    summary["sample_status_counts"] = merge_count_dicts(
        (getattr(result, "summary_json", {}) or {}).get("sample_status_counts") or {} for result in results
    )
    summary["pool_status_counts"] = merge_count_dicts(
        (getattr(result, "summary_json", {}) or {}).get("pool_status_counts") or {} for result in results
    )
    first_summary = getattr(results[0], "summary_json", {}) or {}
    for key in ("boundary_note", "downstream_support"):
        if key in first_summary:
            summary[key] = first_summary[key]
    summary["window_summaries"] = [
        {
            "analysis_windows": list((getattr(result, "summary_json", {}) or {}).get("analysis_windows") or []),
            "market_profile_count": (getattr(result, "summary_json", {}) or {}).get("market_profile_count", 0),
            "market_signal_count": (getattr(result, "summary_json", {}) or {}).get("market_signal_count", 0),
            "comparable_pool_count": (getattr(result, "summary_json", {}) or {}).get("comparable_pool_count", 0),
            "pool_member_count": (getattr(result, "summary_json", {}) or {}).get("pool_member_count", 0),
            "review_required_count": (getattr(result, "summary_json", {}) or {}).get("review_required_count", 0),
        }
        for result in results
    ]
    return summary


def resolve_m07_analysis_windows(analysis_windows: Sequence[str]) -> tuple[str, ...]:
    if analysis_windows:
        return tuple(str(window) for window in analysis_windows)
    return tuple(window.value if hasattr(window, "value") else str(window) for window in M07_ANALYSIS_WINDOWS)


def chunk_sequence(values: Sequence[str], chunk_size: int) -> list[tuple[str, ...]]:
    return [tuple(values[index : index + chunk_size]) for index in range(0, len(values), chunk_size)]


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
) -> tuple[str, str]:
    run_id = stable_cli_uuid(
        "m07-pipeline-run",
        {
            "project_id": project_id,
            "category_code": source_category_code,
            "batch_id": batch_id,
            "sku_scope": sorted(str(sku_code) for sku_code in sku_scope),
            "analysis_windows": list(analysis_windows) or ["all"],
        },
    )
    module_run_id = stable_cli_uuid("m07-module-run", {"run_id": run_id, "module_code": Core3ModuleCode.M07.value})
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
        "sku_count": len(sku_scope),
        "sku_scope": list(sku_scope),
        "analysis_windows": list(analysis_windows) or ["all"],
        "sku_chunk_size": sku_chunk_size,
    }
    pipeline_run.module_version_json = {Core3ModuleCode.M07.value: CORE3_M07_MODULE_VERSION}
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


def finish_m07_cli_run_records(db: Session, *, run_id: str, module_run_id: str, module_result: Any) -> None:
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
        module_run.started_at = getattr(module_result, "started_at", None) or module_run.started_at
        module_run.finished_at = finished_at
        module_run.error_code = "m07_market_profile_failed" if status_value == Core3RunStatus.FAILED.value else None
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
            if status_value in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value}
            else Core3ReleaseGateStatus.NOT_READY.value
        )
        pipeline_run.error_code = "m07_market_profile_failed" if status_value == Core3RunStatus.FAILED.value else None
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
        raise CatForgePipelineError(f"{config['label_cn']}标准卖点 taxonomy 尚未发布，不能生成 SKU 卖点事实画像。")
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
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
    status_value = module_result.status.value if hasattr(module_result.status, "value") else str(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
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
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
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
    status_value = module_result.status.value if hasattr(module_result.status, "value") else str(module_result.status)
    if module_result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING} or status_value in {"success", "warning"}:
        db.commit()
    else:
        db.rollback()
    result_status = "ok" if status_value == "success" else "warning" if status_value == "warning" else "error"
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


def resolve_source_batch_id(db: Session, project_id: str, source_category_code: str, batch_id: str) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    resolved = db.execute(
        select(entities.Core3SourceBatch.batch_id)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.category_code == source_category_code)
        .order_by(entities.Core3SourceBatch.created_at.desc(), entities.Core3SourceBatch.batch_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not resolved:
        raise CatForgePipelineError(f"没有找到项目 {project_id} / {source_category_code} 的可用 source batch。")
    return str(resolved)


def should_run_param_profile(question: str) -> bool:
    return any(word in question for word in ("参数画像", "参数事实", "标准参数", "生成", "重跑", "重新", "更新", "数据准备", "准备好可以分析"))


def should_run_value_battlefield(question: str) -> bool:
    normalized = normalize_token(question)
    if "价值战场" not in question and "战场图谱" not in question and "battlefield" not in normalized:
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
    if not any(word in question for word in ("目标客群", "目标客户", "目标用户", "客群画像", "客户画像", "人群画像")) and "targetgroup" not in normalized:
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
    if not any(word in question for word in ("用户任务", "使用任务", "主任务", "任务画像", "购买目的", "使用目的")) and "usertask" not in normalized:
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
        return any(word in normalized for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算", "量价", "市场画像"))
    return any(word in normalized for word in ("量价画像", "市场量价", "价格区间", "尺寸区间")) and any(
        word in normalized for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算")
    )


def should_run_comment_profile(question: str) -> bool:
    normalized = normalize_token(question)
    if any(word in question for word in ("评论事实画像", "评论画像", "用户评价画像", "评价事实画像")):
        return any(word in normalized for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算", "准备好可以分析"))
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


def extract_battlefield_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\bBF_[A-Z0-9_]+\b", question.upper())))


def extract_target_group_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\bTG_[A-Z0-9_]+\b", question.upper())))


def extract_user_task_scope(question: str) -> list[str]:
    return sorted(set(re.findall(r"\bTASK_[A-Z0-9_]+\b", question.upper())))


def extract_analysis_windows(question: str) -> list[str]:
    normalized = normalize_token(question)
    windows: list[str] = []
    if any(token in normalized for token in ("全量", "全观察", "完整窗口", "fullobservedwindow")):
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
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


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
    if result.get("status") not in {"ok", "warning"}:
        return result.get("error") or json.dumps(to_jsonable(result), ensure_ascii=False)
    label = result.get("product_category_label_cn") or result.get("product_category")
    summary = result.get("summary") or {}
    is_claim_profile = isinstance(summary, dict) and "claim_fact_count" in summary
    is_comment_profile = isinstance(summary, dict) and "comment_fact_count" in summary
    is_market_profile = isinstance(summary, dict) and "market_profile_count" in summary
    is_target_group_profile = isinstance(summary, dict) and "target_group_count" in summary
    is_value_battlefield_profile = isinstance(summary, dict) and "battlefield_count" in summary
    if is_market_profile:
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
        lines.append(f"taxonomy={result['taxonomy_version']}；rule={result['rule_version']}")
    else:
        lines.append(f"rule={result['rule_version']}")
    if result.get("warnings"):
        lines.append("warnings: " + ", ".join(result["warnings"]))
    if isinstance(summary, dict):
        if is_market_profile:
            lines.append(
                "画像数："
                f"{summary.get('market_profile_count', 0)}；市场信号：{summary.get('market_signal_count', 0)}；"
                f"可比池：{summary.get('comparable_pool_count', 0)}；池成员：{summary.get('pool_member_count', 0)}；"
                f"需复核：{summary.get('review_required_count', 0)}"
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
            lines.append(f"主客群分布：{json.dumps(summary.get('primary_target_group_counts', {}), ensure_ascii=False, sort_keys=True)}")
        elif is_value_battlefield_profile:
            lines.append(
                "画像数："
                f"{summary.get('profile_count', 0)}；战场分数：{summary.get('score_count', 0)}；"
                f"图谱：{summary.get('graph_snapshot_count', 0)}；战场数：{summary.get('battlefield_count', 0)}"
            )
            lines.append(f"主战场分布：{json.dumps(summary.get('primary_battlefield_counts', {}), ensure_ascii=False, sort_keys=True)}")
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
