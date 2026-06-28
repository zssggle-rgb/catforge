"""Agent-facing CatForge analyst CLI framework.

The CLI is intentionally a thin adapter over ``CatForgeAnalystService``. It
provides stable command names, shared context arguments, and deterministic JSON
output so OpenClaw/Claude Code skills can compose atomic abilities and SOPs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.core3_real_data.analyst import competitor_answer as competitor_answer_renderer
from app.services.core3_real_data.analyst.analyst_schemas import AnalystStatus
from app.services.core3_real_data.analyst.analyst_service import (
    ATOM_COMMANDS,
    LATEST_BATCH,
    SOP_COMMANDS,
    CatForgeAnalystError,
    CatForgeAnalystService,
)


DEFAULT_PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_CATEGORY_CODE = "TV"
DEFAULT_PRODUCT_CATEGORY = "tv"
DEFAULT_MARKET_WINDOW = "full_observed_window"
DEFAULT_ANALYSIS_POPULATION = "fact_complete_with_comment"
DEFAULT_CANDIDATE_LIMIT = 20

ATOM_COMMAND_ORDER = (
    "resolve-sku",
    "sku-fact-brief",
    "same-size-price-candidates",
    "semantic-overlap",
    "sales-overlap",
    "param-claim-overlap",
    "comment-support",
    "semantic-dimension-space",
    "opportunity-gaps",
    "claim-value-space",
    "sku-claim-value",
    "claim-contribution",
    "claim-opportunity-gaps",
    "claim-value-compare",
)

SOP_COMMAND_ORDER = (
    "competitor-set",
    "why-sales-diff",
    "premium-claim-drivers",
    "battlefield-space",
    "battlefield-opportunity",
    "sku-business-brief",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            result = run_analyst_command(
                db,
                command=args.command,
                project_id=args.project_id,
                category_code=args.category_code,
                batch_id=args.batch_id,
                product_category=args.product_category,
                market_window=args.market_window,
                analysis_population=args.analysis_population,
                ability_type=getattr(args, "ability_type", None),
                question=" ".join(getattr(args, "question", ()) or ()),
                query=getattr(args, "query", None),
                sku_code=getattr(args, "sku_code", None),
                model_name=getattr(args, "model_name", None),
                candidate_sku_code=getattr(args, "candidate_sku_code", None),
                dimension_type=getattr(args, "dimension_type", None),
                dimension_code=getattr(args, "dimension_code", None),
                brand_name=getattr(args, "brand_name", None),
                size_tier=getattr(args, "size_tier", None),
                price_band=getattr(args, "price_band", None),
                claim_code=getattr(args, "claim_code", None),
                param_code=getattr(args, "param_code", None),
                user_task_code=getattr(args, "user_task_code", None),
                target_group_code=getattr(args, "target_group_code", None),
                battlefield_code=getattr(args, "battlefield_code", None),
                role=getattr(args, "role", None),
                limit=getattr(args, "limit", DEFAULT_CANDIDATE_LIMIT),
                answer_style=getattr(args, "answer_style", None),
                with_report=getattr(args, "with_report", None),
                top_n=getattr(args, "top_n", None),
                max_chat_chars=getattr(args, "max_chat_chars", None),
                report_title=getattr(args, "report_title", None),
            )
            attach_feishu_card_delivery(result, args)
    except CatForgeAnalystError as exc:
        result = {
            "status": AnalystStatus.ERROR.value,
            "command": getattr(args, "command", None),
            "message_cn": str(exc),
            "error": str(exc),
        }
        emit_result(result, args.format)
        return 1

    emit_result(result, args.format, feishu_card_only=getattr(args, "feishu_card_only", False))
    return 0 if result.get("status") not in {"error"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.catforge_analyst",
        description="Run CatForge analyst atomic abilities and SOP routers for market-analysis agents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    abilities = subparsers.add_parser("list-abilities", help="List available analyst atoms, SOPs, and router abilities.")
    add_context_args(abilities)
    abilities.add_argument("--ability-type", choices=("atom", "sop", "router"), help="Optional ability type filter.")
    add_format_arg(abilities)

    for command in ATOM_COMMAND_ORDER:
        command_parser = subparsers.add_parser(command, help=f"Run analyst atom: {command}.")
        add_context_args(command_parser)
        add_sku_args(command_parser)
        add_pair_args(command_parser)
        add_dimension_args(command_parser)
        command_parser.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
        if command == "sku-claim-value":
            add_answer_args(command_parser)
        add_format_arg(command_parser)

    for command in SOP_COMMAND_ORDER:
        command_parser = subparsers.add_parser(command, help=f"Run analyst SOP: {command}.")
        add_context_args(command_parser)
        add_sku_args(command_parser)
        add_pair_args(command_parser)
        add_dimension_args(command_parser)
        command_parser.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
        add_answer_args(command_parser)
        add_format_arg(command_parser)

    ask = subparsers.add_parser("ask", help="Route a natural-language analyst question to an atom or SOP.")
    add_context_args(ask)
    add_sku_args(ask)
    add_pair_args(ask)
    add_dimension_args(ask)
    ask.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    add_answer_args(ask)
    ask.add_argument("question", nargs="+", help="Natural-language question.")
    add_format_arg(ask)
    return parser


def add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE)
    parser.add_argument("--batch-id", default=LATEST_BATCH)
    parser.add_argument("--product-category", choices=("tv", "ac"), default=DEFAULT_PRODUCT_CATEGORY)
    parser.add_argument("--market-window", default=DEFAULT_MARKET_WINDOW)
    parser.add_argument(
        "--analysis-population",
        choices=("fact_complete_with_comment", "all_semantic_profiles"),
        default=DEFAULT_ANALYSIS_POPULATION,
    )


def add_sku_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", help="Natural SKU/model query.")
    parser.add_argument("--sku-code", help="Exact SKU code, such as TV00029112.")
    parser.add_argument("--model-name", help="Exact or fuzzy model name, such as 65E7Q.")


def add_pair_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate-sku-code", help="Candidate SKU code for pairwise comparison commands.")


def add_dimension_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dimension-type", choices=("market_pool", "user_task", "target_group", "battlefield"), help="Semantic dimension type.")
    parser.add_argument("--dimension-code", help="Semantic dimension code, such as BF_LARGE_SCREEN_VALUE_UPGRADE.")
    parser.add_argument("--brand-name", help="Optional brand filter for dimension-space commands.")
    parser.add_argument("--size-tier", help="Optional five-tier size filter.")
    parser.add_argument("--price-band", help="Optional size-tier price band filter.")
    parser.add_argument("--claim-code", help="Optional claim code filter for comment-support.")
    parser.add_argument("--param-code", help="Optional param code filter for comment-support.")
    parser.add_argument("--user-task-code", help="Optional user task code filter for comment-support.")
    parser.add_argument("--target-group-code", help="Optional target group code filter for comment-support.")
    parser.add_argument("--battlefield-code", help="Optional battlefield code filter for comment-support.")
    parser.add_argument("--role", help="Optional M12C claim value role filter, such as premium_driver_estimated.")


def add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="json")


def add_answer_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--answer-style", choices=("raw", "xiaoao"), default="raw")
    parser.add_argument("--with-report", choices=("none", "markdown", "feishu-doc"), default="none")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--max-chat-chars", type=int, default=600)
    parser.add_argument("--report-title")
    parser.add_argument("--feishu-reply-message-id", help="Feishu message_id to reply with the generated competitor card.")
    parser.add_argument("--feishu-reply-in-thread", action="store_true", help="Send the Feishu card as a thread reply.")
    parser.add_argument("--feishu-card-idempotency-key", help="Optional idempotency key for Feishu card reply.")
    parser.add_argument("--feishu-card-only", action="store_true", help="For text output, print only Feishu card delivery status.")


def list_analyst_abilities(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    ability_type: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="list-abilities",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        ability_type=ability_type,
    )


def resolve_sku(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="resolve-sku",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def sku_fact_brief(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="sku-fact-brief",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def same_size_price_candidates(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="same-size-price-candidates",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def semantic_overlap(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="semantic-overlap",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
    )


def sales_overlap(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="sales-overlap",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
    )


def param_claim_overlap(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="param-claim-overlap",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
    )


def comment_support(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    claim_code: str | None = None,
    param_code: str | None = None,
    user_task_code: str | None = None,
    target_group_code: str | None = None,
    battlefield_code: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="comment-support",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        claim_code=claim_code,
        param_code=param_code,
        user_task_code=user_task_code,
        target_group_code=target_group_code,
        battlefield_code=battlefield_code,
    )


def opportunity_gaps(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="opportunity-gaps",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def claim_value_space(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    size_tier: str | None = None,
    price_band: str | None = None,
    claim_code: str | None = None,
    role: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="claim-value-space",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        size_tier=size_tier,
        price_band=price_band,
        claim_code=claim_code,
        role=role,
        limit=limit,
    )


def sku_claim_value(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    claim_code: str | None = None,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    size_tier: str | None = None,
    price_band: str | None = None,
    role: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    answer_style: str = "raw",
    with_report: str = "none",
    max_chat_chars: int = 600,
    report_title: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="sku-claim-value",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        claim_code=claim_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        size_tier=size_tier,
        price_band=price_band,
        role=role,
        limit=limit,
        answer_style=answer_style,
        with_report=with_report,
        max_chat_chars=max_chat_chars,
        report_title=report_title,
    )


def claim_contribution(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    size_tier: str | None = None,
    price_band: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="claim-contribution",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        size_tier=size_tier,
        price_band=price_band,
        limit=limit,
    )


def claim_opportunity_gaps(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="claim-opportunity-gaps",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        limit=limit,
    )


def claim_value_compare(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="claim-value-compare",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        limit=limit,
    )


def competitor_set(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    answer_style: str = "raw",
    with_report: str = "none",
    top_n: int = 3,
    max_chat_chars: int = 600,
    report_title: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="competitor-set",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
        answer_style=answer_style,
        with_report=with_report,
        top_n=top_n,
        max_chat_chars=max_chat_chars,
        report_title=report_title,
    )


def sku_business_brief(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="sku-business-brief",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def why_sales_diff(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="why-sales-diff",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
    )


def premium_claim_drivers(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="premium-claim-drivers",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def battlefield_space(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    market_window: str = DEFAULT_MARKET_WINDOW,
    dimension_code: str | None = None,
    query: str | None = None,
    brand_name: str | None = None,
    size_tier: str | None = None,
    price_band: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="battlefield-space",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        analysis_population=analysis_population,
        market_window=market_window,
        dimension_code=dimension_code,
        query=query,
        brand_name=brand_name,
        size_tier=size_tier,
        price_band=price_band,
        limit=limit,
    )


def battlefield_opportunity(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="battlefield-opportunity",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        limit=limit,
    )


def semantic_dimension_space(
    db: Session,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    market_window: str = DEFAULT_MARKET_WINDOW,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    query: str | None = None,
    brand_name: str | None = None,
    size_tier: str | None = None,
    price_band: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="semantic-dimension-space",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        analysis_population=analysis_population,
        market_window=market_window,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        query=query,
        brand_name=brand_name,
        size_tier=size_tier,
        price_band=price_band,
        limit=limit,
    )


def answer_natural_language(
    db: Session,
    *,
    question: str,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    brand_name: str | None = None,
    size_tier: str | None = None,
    price_band: str | None = None,
    claim_code: str | None = None,
    param_code: str | None = None,
    user_task_code: str | None = None,
    target_group_code: str | None = None,
    battlefield_code: str | None = None,
    role: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    answer_style: str = "raw",
    with_report: str = "none",
    top_n: int = 3,
    max_chat_chars: int = 600,
    report_title: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="ask",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        question=question,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        brand_name=brand_name,
        size_tier=size_tier,
        price_band=price_band,
        claim_code=claim_code,
        param_code=param_code,
        user_task_code=user_task_code,
        target_group_code=target_group_code,
        battlefield_code=battlefield_code,
        role=role,
        limit=limit,
        answer_style=answer_style,
        with_report=with_report,
        top_n=top_n,
        max_chat_chars=max_chat_chars,
        report_title=report_title,
    )


def run_analyst_command(
    db: Session,
    *,
    command: str,
    project_id: str = DEFAULT_PROJECT_ID,
    category_code: str = DEFAULT_CATEGORY_CODE,
    batch_id: str = LATEST_BATCH,
    product_category: str = DEFAULT_PRODUCT_CATEGORY,
    market_window: str = DEFAULT_MARKET_WINDOW,
    analysis_population: str = DEFAULT_ANALYSIS_POPULATION,
    **kwargs: Any,
) -> dict[str, Any]:
    if command not in {"list-abilities", "ask", *ATOM_COMMANDS, *SOP_COMMANDS}:
        raise CatForgeAnalystError(f"不支持的 analyst 命令：{command}")

    product_category = _infer_product_category(product_category, kwargs)
    category_code = _infer_category_code(category_code, product_category, kwargs)
    service = CatForgeAnalystService(db, project_id=project_id, category_code=category_code)
    context = service.build_context(
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        resolve_latest=command != "list-abilities",
    )
    if command == "list-abilities":
        return service.list_abilities(context, ability_type=kwargs.get("ability_type"))
    return service.dispatch(command, context, **_clean_kwargs(kwargs))


def _infer_product_category(product_category: str, kwargs: dict[str, Any]) -> str:
    normalized = (product_category or DEFAULT_PRODUCT_CATEGORY).strip().lower()
    if normalized in {"ac", "空调"}:
        return "ac"
    if normalized in {"tv", "电视", "彩电"} and _context_mentions_ac(kwargs):
        return "ac"
    return normalized


def _infer_category_code(category_code: str, product_category: str, kwargs: dict[str, Any]) -> str:
    normalized = (category_code or DEFAULT_CATEGORY_CODE).strip().upper()
    if normalized == DEFAULT_CATEGORY_CODE and ((product_category or "").strip().upper() == "AC" or _context_mentions_ac(kwargs)):
        return "AC"
    return normalized


def _context_mentions_ac(kwargs: dict[str, Any]) -> bool:
    text_parts: list[str] = []
    for key in ("question", "query", "sku_code", "candidate_sku_code", "model_name"):
        value = kwargs.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    text = " ".join(text_parts)
    return bool(re.search(r"(?<![A-Za-z0-9])AC\d{6,}(?![A-Za-z0-9])", text, re.IGNORECASE) or re.search(r"空调", text))


def attach_feishu_card_delivery(result: dict[str, Any], args: argparse.Namespace) -> None:
    reply_message_id = getattr(args, "feishu_reply_message_id", None)
    if not reply_message_id:
        return
    competitor_answer = (result.get("result") or {}).get("competitor_answer") or {}
    delivery = competitor_answer_renderer.publish_feishu_card_reply(
        card=competitor_answer.get("feishu_card_payload"),
        reply_message_id=reply_message_id,
        reply_in_thread=bool(getattr(args, "feishu_reply_in_thread", False)),
        idempotency_key=getattr(args, "feishu_card_idempotency_key", None),
    )
    if not isinstance(result.get("result"), dict):
        result["result"] = {}
    if not isinstance(result["result"].get("competitor_answer"), dict):
        result["result"]["competitor_answer"] = {}
    result["result"]["competitor_answer"]["feishu_card_delivery"] = delivery.to_dict()


def emit_result(result: dict[str, Any], output_format: str, *, feishu_card_only: bool = False) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, default=json_default, indent=2, sort_keys=True))
        return
    card_delivery = _feishu_card_delivery(result)
    if card_delivery:
        delivery_text = format_feishu_card_delivery_text(result)
        if delivery_text:
            print(delivery_text)
            return
    if feishu_card_only:
        print("未发送飞书竞品看板卡片：缺少发送结果。")
        return
    business_text = format_business_text(result)
    if business_text:
        print(business_text)
        return
    message = result.get("message_cn")
    if message:
        print(message)
    outline = result.get("answer_outline") or []
    for item in outline:
        print(f"- {item}")
    if not message and not outline:
        print(json.dumps(result, ensure_ascii=False, default=json_default, indent=2, sort_keys=True))


def _feishu_card_delivery(result: dict[str, Any]) -> dict[str, Any]:
    competitor_answer = (result.get("result") or {}).get("competitor_answer") or {}
    delivery = competitor_answer.get("feishu_card_delivery")
    return delivery if isinstance(delivery, dict) else {}


def format_feishu_card_delivery_text(result: dict[str, Any]) -> str:
    competitor_answer = (result.get("result") or {}).get("competitor_answer") or {}
    delivery = _feishu_card_delivery(result)
    if delivery.get("status") == "sent":
        return str(delivery.get("message_cn") or "已发送飞书竞品看板卡片。")
    if delivery.get("message_cn"):
        return str(delivery["message_cn"])
    if delivery.get("status") == "failed":
        return "飞书卡片发送失败。"
    if delivery.get("status"):
        return "未发送飞书竞品看板卡片。"
    return str(competitor_answer.get("short_answer") or "")


def format_business_text(result: dict[str, Any]) -> str:
    payload = result.get("result") or {}
    if result.get("status") == "ambiguous" and payload.get("candidates"):
        return _format_ambiguous_sku_text(result)
    competitor_answer = payload.get("competitor_answer") or {}
    if competitor_answer.get("short_answer"):
        return str(competitor_answer["short_answer"])
    claim_value_answer = payload.get("claim_value_answer") or {}
    if claim_value_answer.get("short_answer"):
        return str(claim_value_answer["short_answer"])
    if "competitor_set" in payload:
        return _format_competitor_set_text(result)
    if "why_sales_diff" in payload:
        return _format_why_sales_diff_text(result)
    if "sku_claim_value" in payload:
        return _format_sku_claim_value_text(result)
    if "claim_contribution" in payload:
        return _format_claim_contribution_text(result)
    if "claim_value_space" in payload:
        return _format_claim_value_space_text(result)
    return ""


def _format_ambiguous_sku_text(result: dict[str, Any]) -> str:
    candidates = (result.get("result") or {}).get("candidates") or []
    lines = ["匹配到多个 SKU，请选择一个后继续分析："]
    for index, candidate in enumerate(candidates[:10], start=1):
        name = _brand_model(candidate)
        sku_code = candidate.get("sku_code") or ""
        size = _format_number(candidate.get("screen_size_inch"))
        price = _format_money(candidate.get("weighted_price"))
        details = [item for item in [f"{size}英寸" if size else "", price] if item]
        suffix = f"（{'，'.join(details)}）" if details else ""
        lines.append(f"{index}. {name}，SKU：{sku_code}{suffix}")
    return "\n".join(lines)


def _format_competitor_set_text(result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    competitor_set_payload = (result.get("result") or {}).get("competitor_set") or {}
    candidates = competitor_set_payload.get("candidates") or []
    if not candidates:
        target_name = _brand_model(target)
        return f"当前可观测线上样本中，{target_name} 暂未找到可稳定比较的同尺寸同价位竞品。"

    top_candidates = _select_key_competitors(candidates)
    top_names = "、".join(_brand_model(item.get("candidate") or {}) for item in top_candidates)
    target_name = _brand_model(target)
    size = _format_number(target.get("screen_size_inch"))
    price = _format_money(target.get("weighted_price") or target.get("price_wavg"))
    price_band = _price_band_cn(target.get("price_band_in_size_tier"))
    sales = _format_volume(target.get("avg_weekly_sales_volume"))

    identity_parts = [target_name]
    if size:
        identity_parts.append(f"{size}英寸")
    if price_band:
        identity_parts.append(price_band)
    if price:
        identity_parts.append(f"当前线上均价约{price}")
    if sales:
        identity_parts.append(f"当前周均销量约{sales}台")

    lines: list[str] = [
        f"结论：{'、'.join(identity_parts)}，当前最值得重点比较的三款竞品是：{top_names}。",
        "",
        "判断依据：",
    ]
    for index, item in enumerate(top_candidates, start=1):
        lines.append(f"{index}. {_format_competitor_line(item)}")

    remaining = [item for item in candidates if item not in top_candidates]
    if remaining:
        lines.extend(["", "补充观察："])
        for item in remaining[:4]:
            cand = item.get("candidate") or {}
            role = _competitor_role(item)
            price_gap = _format_price_gap(cand.get("price_gap_pct_to_target"), cand.get("price_gap_to_target"))
            sales_text = _format_volume(cand.get("avg_weekly_sales_volume"))
            detail_parts = [role]
            if price_gap:
                detail_parts.append(price_gap)
            if sales_text:
                detail_parts.append(f"周均销量约{sales_text}台")
            lines.append(f"- {_brand_model(cand)}：{'；'.join(detail_parts)}。")

    lines.extend(
        [
            "",
            "分析过程：",
            "- 先限定竞争池：优先看同尺寸、同尺寸内相近价格带的产品，避免把不同空间和预算段的电视混在一起比较。",
            "- 再看需求重合：价值战场、用户任务和目标客群越接近，越可能在同一批用户心智中相互替代。",
            "- 再看产品重合：关键参数和卖点越接近，用户在货架上越容易做横向比较。",
            "- 最后用重叠在售周的周均销量做市场验证，不用累计销量判断谁更强。",
            "",
            "口径与限制：基于当前可观测线上样本；线下渠道、广告投放、库存、促销资源不在当前数据内。",
        ]
    )
    limitations = [_sanitize_business_limitation(item) for item in result.get("limitations") or [] if item]
    limitations = [item for item in limitations if item]
    if limitations:
        lines.append(f"补充限制：{'；'.join(str(item) for item in limitations[:3])}。")
    return "\n".join(lines)


def _format_why_sales_diff_text(result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    payload = ((result.get("result") or {}).get("why_sales_diff") or {})
    candidate = payload.get("candidate") or {}
    sales = payload.get("sales_overlap") or {}
    semantic = payload.get("semantic_overlap") or {}
    param_claim = payload.get("param_claim_overlap") or {}
    comment_support = payload.get("comment_support") or {}

    target_name = _brand_model(target)
    candidate_name = _brand_model(candidate)
    target_price = _format_money(target.get("weighted_price") or target.get("price_wavg"))
    candidate_price = _format_money(candidate.get("weighted_price") or candidate.get("price_wavg"))
    target_sales = _format_volume(target.get("avg_weekly_sales_volume"))
    candidate_sales = _format_volume(candidate.get("avg_weekly_sales_volume"))
    price_gap = _pair_price_gap_text(target, candidate)
    size = _format_number(target.get("screen_size_inch"))
    price_band = _price_band_cn(target.get("price_band_in_size_tier"))

    overlap_weeks = sales.get("overlap_week_count")
    comparison = sales.get("comparison") or {}
    volume_gap = _decimal(comparison.get("target_vs_candidate_avg_weekly_volume_gap"))
    volume_ratio = _decimal(comparison.get("target_vs_candidate_avg_weekly_volume_ratio"))
    amount_ratio = _decimal(comparison.get("target_vs_candidate_avg_weekly_amount_ratio"))
    semantic_score = _format_percent(semantic.get("semantic_overlap_score"))
    param_score = _format_percent(param_claim.get("param_claim_overlap_score"))

    target_available = ((comment_support.get("target") or {}).get("available_summary") or {})
    candidate_available = ((comment_support.get("candidate") or {}).get("available_summary") or {})
    target_claims = _claim_names(target_available.get("supported_claim_codes") or [])
    candidate_claims = _claim_names(candidate_available.get("supported_claim_codes") or [])
    candidate_risks = _claim_names(candidate_available.get("contradicted_claim_codes") or [])

    lead_text = _sales_lead_text(target_name, candidate_name, volume_gap, volume_ratio)
    identity = [f"{target_name} 与 {candidate_name}"]
    if overlap_weeks:
        identity.append(f"{overlap_weeks} 个重叠在售周")
    if target_price and candidate_price:
        identity.append(f"均价分别约 {target_price} / {candidate_price}")
    if target_sales and candidate_sales:
        identity.append(f"周均销量约 {target_sales} 台 / {candidate_sales} 台")
    segment = "、".join(part for part in (f"{size}英寸" if size else "", price_band) if part)
    segment_text = f"同为{segment}产品，" if segment else ""

    lines = [
        f"结论：{candidate_name} 被列为{target_name} 的第一竞品是合理的。它们{segment_text}价格非常接近，目标用户和使用场景高度重合，且重叠在售周销量处在同一竞争量级。",
        "",
        "核心依据：",
        f"1. 市场池相同：{'；'.join(identity)}。{price_gap}",
    ]
    if semantic_score:
        lines.append(f"2. 需求重合高：用户任务、目标客群和价值战场的综合重合度约 {semantic_score}，说明两款产品会被同一批用户放在一起比较。")
    if param_score:
        lines.append(f"3. 产品表达可比：参数和卖点重合度约 {param_score}，不是只靠价格接近，而是在画质、影音、智能/游戏等能力上形成横向对比。")
    if lead_text:
        lines.append(f"4. 销量验证成立：按重叠在售周周均销量看，{lead_text}；这说明它不是边缘候选，而是真实处在同一销售竞争带内。")
    if amount_ratio:
        lines.append(f"5. 销额表现也接近：{target_name} 相对 {candidate_name} 的重叠周均销额约为 {_format_ratio(amount_ratio)}，价格与销量共同支撑其直接竞争关系。")

    if target_claims or candidate_claims:
        lines.extend(["", "卖点和用户反馈："])
        if target_claims:
            lines.append(f"- {target_name} 的用户评论更集中支撑：{'、'.join(target_claims[:6])}。")
        if candidate_claims:
            lines.append(f"- {candidate_name} 的用户评论更集中支撑：{'、'.join(candidate_claims[:6])}。")
        if candidate_risks:
            lines.append(f"- {candidate_name} 也有需要复核的用户反馈风险：{'、'.join(candidate_risks[:4])}。")

    lines.extend(
        [
            "",
            "怎么理解“第一竞品”：",
            "- 它不是因为销量最接近才被选中，而是先满足同尺寸、同价位，再满足高需求重合和产品能力可比，最后由重叠周销量验证。",
            f"- 因此它适合作为{target_name} 的第一对标对象，用来比较价格策略、画质/影音卖点、游戏体育场景和用户评论认可度。",
            "",
            "口径与限制：当前判断基于可观测线上样本；线下渠道、广告投放、库存和促销资源不在当前数据内。",
        ]
    )
    limitations = [_sanitize_business_limitation(item) for item in result.get("limitations") or [] if item]
    limitations = [item for item in limitations if item]
    if limitations:
        lines.append(f"补充限制：{'；'.join(str(item) for item in limitations[:3])}。")
    return "\n".join(lines)


def _format_sku_claim_value_text(result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    payload = ((result.get("result") or {}).get("sku_claim_value") or {})
    rows = [row for row in payload.get("claim_values") or [] if isinstance(row, dict)]
    summary_rows = [row for row in payload.get("sku_level_claim_values") or [] if isinstance(row, dict)]
    if not rows and summary_rows:
        return _format_sku_level_claim_value_text(target, summary_rows)
    if not rows:
        return result.get("message_cn") or "当前 SKU 没有 M12C 卖点价值量化结果。"
    lines = [f"{_brand_model(target)} 的卖点价值量化结果："]
    groups = _claim_value_cli_groups(rows)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for group in groups:
        by_category.setdefault(str(group.get("category") or ""), []).append(group)
    for category in _claim_value_cli_category_order():
        category_groups = by_category.get(category, [])
        if not category_groups:
            continue
        lines.append(f"{category}：")
        for group in category_groups[:5]:
            sales_total = _format_volume(group["sales_total"])
            quantified = bool(group.get("battlefields")) and category not in _claim_value_cli_text_only_categories()
            lines.append(
                f"- {group['claim_name']}：战场可解释价差合计{(_format_money(group['price_total']) or '暂不量化') if quantified else '不作为正向量化'}；"
                f"战场可解释销量合计{(f'{sales_total}台/周' if sales_total else '暂不量化') if quantified else '不作为正向量化'}；"
                f"覆盖价值战场：{'、'.join(group['battlefields'][:4]) if group['battlefields'] else '价值战场暂未形成稳定量化'}。"
            )
            if quantified:
                for item in group.get("quant_groups", [])[:3]:
                    row = item["representative"]
                    pool_effect = row.get("pool_effect") or {}
                    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
                    lines.append(
                        f"  - {'、'.join(item.get('battlefields') or []) or row.get('context_name') or row.get('context_code') or '当前价值战场'}："
                        f"可比产品价格差异{_format_money(pool_effect.get('pool_claim_price_delta_abs')) or '未知'}，"
                        f"销量差异{_format_volume(pool_effect.get('pool_claim_weekly_sales_delta_abs')) or '未知'}台/周；"
                        f"本品可解释价差份额{_format_money(sku_excess.get('sku_excess_price_explained_abs') or sku_excess.get('price_premium_abs')) or '不作为正向分摊'}，"
                        f"可解释销量份额{_format_volume(sku_excess.get('sku_excess_weekly_sales_explained_abs') or sku_excess.get('weekly_sales_lift_abs')) or '不作为正向分摊'}台/周。"
                    )
    lines.append("说明：战场合计只汇总同一分类、同一卖点在价值战场中的去重量化结果；多个战场共用同一组可比池差异和本品解释份额时，合并展示、只计一次；目标客群、用户任务和整体市场池只作为解释证据，不参与求和。")
    return "\n".join(lines)


def _format_sku_level_claim_value_text(target: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [f"{_brand_model(target)} 的用户卖点支付价值分析："]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        category = str(row.get("business_claim_type_cn") or "未分类卖点")
        grouped.setdefault(category, []).append(row)
    positive_categories = {"高溢价卖点", "份额转化卖点", "客户获得价值卖点"}
    if not any(grouped.get(category) for category in positive_categories):
        lines.append("当前没有形成可稳定量化的正向用户支付价值卖点；以下结果更多用于说明入围门槛、待激活机会、竞品拦截和价格压力。")
    for category in _claim_value_cli_category_order():
        items = grouped.get(category, [])
        if not items:
            continue
        lines.append(f"{category}：")
        for item in items[:5]:
            claim_name = str(item.get("claim_name") or item.get("claim_code") or "未命名卖点")
            price = _decimal(item.get("sku_level_user_payment_value_abs")) or Decimal("0")
            sales = _decimal(item.get("sku_level_weekly_sales_lift_abs")) or Decimal("0")
            contexts = "、".join(str(value) for value in (item.get("main_contexts") or [])[:4]) or "相关价值战场"
            evidence = str(item.get("evidence_summary_cn") or "").strip()
            lines.append(
                f"- {claim_name}：{_sku_level_claim_value_sentence(category, price, sales)}；"
                f"主要成立场景：{contexts}。"
                f"{evidence}"
            )
            if category in positive_categories:
                for detail in _sku_level_positive_context_lines(item):
                    lines.append(detail)
    lines.append("说明：以上为 SKU 层汇总结果，计算时先在单个价值战场内判断卖点支付价值，再按战场相关度汇总；用户任务、目标客群和整体市场池作为解释证据，不直接重复累加。")
    return "\n".join(lines)


def _sku_level_positive_context_lines(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for context in [value for value in (item.get("context_values") or []) if isinstance(value, dict)][:3]:
        price = _format_money(context.get("price_premium_abs"))
        sales = _format_volume(context.get("weekly_sales_lift_abs"))
        pool_effect = context.get("pool_effect") or {}
        pool_price = _format_money(pool_effect.get("pool_claim_price_delta_abs"))
        pool_sales = _format_volume(pool_effect.get("pool_claim_weekly_sales_delta_abs"))
        context_name = str(context.get("context_name") or context.get("context_code") or "当前价值战场")
        parts = []
        if price:
            parts.append(f"本品可解释价差约{price}")
        if sales:
            parts.append(f"可解释销量约{sales}台/周")
        if pool_price:
            parts.append(f"可比池卖点组价格差异约{pool_price}")
        if pool_sales:
            parts.append(f"可比池卖点组销量差异约{pool_sales}台/周")
        if parts:
            lines.append(f"  - {context_name}：{'；'.join(parts)}。")
    return lines


def _sku_level_claim_value_sentence(category: str, price: Decimal, sales: Decimal) -> str:
    price_text = _format_money(price) or "暂不量化"
    sales_text = f"{_format_volume(sales)}台/周" if _format_volume(sales) else "暂不量化"
    if category == "高溢价卖点":
        return f"用户卖点支付价值约{price_text}，销量解释约{sales_text}"
    if category == "份额转化卖点":
        return f"价格溢价不一定显著，销量解释约{sales_text}"
    if category == "客户获得价值卖点":
        return f"更主要体现为用户觉得更值，当前可解释价差约{price_text}，销量解释约{sales_text}"
    if category == "门槛卖点":
        return "属于购买入围门槛，有了不一定加价，缺失会削弱入围"
    if category == "待激活卖点":
        return "已有产品事实或厂家表达，但用户感知和市场验证还不足"
    if category == "厂家主张卖点":
        return "当前主要是厂家表达，尚未形成稳定用户支付价值"
    if category == "竞品拦截卖点":
        return "竞品已经形成有效表达或市场验证，本品存在被拦截风险"
    if category == "价格压力卖点":
        return "卖点、参数或评论没有支撑当前价格，可能削弱成交理由"
    return "样本或对照组不足，暂作为观察线索"


def _claim_value_cli_category_order() -> list[str]:
    return [
        "高溢价卖点",
        "份额转化卖点",
        "客户获得价值卖点",
        "门槛卖点",
        "待激活卖点",
        "厂家主张卖点",
        "竞品拦截卖点",
        "价格压力卖点",
        "样本不足待复核",
    ]


def _claim_value_cli_text_only_categories() -> set[str]:
    return {
        "待激活卖点",
        "厂家主张卖点",
        "竞品拦截卖点",
        "价格压力卖点",
        "样本不足待复核",
    }


def _claim_value_cli_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        category = _claim_value_cli_category(row)
        claim_key = str(row.get("claim_code") or row.get("claim_name") or "")
        if not claim_key:
            claim_key = f"claim-{len(grouped)}"
        key = (category, claim_key)
        if key not in grouped:
            grouped[key] = {
                "category": category,
                "claim_name": str(row.get("claim_name") or row.get("claim_code") or "未命名卖点"),
                "battlefield_rows": [],
                "price_total": Decimal("0"),
                "sales_total": Decimal("0"),
                "battlefields": [],
            }
        group = grouped[key]
        if str(row.get("context_type") or "") != "battlefield":
            continue
        group["battlefield_rows"].append(row)
        battlefield = str(row.get("context_name") or row.get("context_code") or "").strip()
        if battlefield and battlefield not in group["battlefields"]:
            group["battlefields"].append(battlefield)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    claim_keys_with_quantified_battlefields = {
        original_key[1]
        for original_key, group in grouped.items()
        if group.get("battlefield_rows")
        and str(group.get("category") or "") in {"高溢价卖点", "份额转化卖点", "客户获得价值卖点", "门槛卖点"}
    }
    for original_key, group in grouped.items():
        category = str(group.get("category") or "")
        if category in {"高溢价卖点", "份额转化卖点", "客户获得价值卖点", "门槛卖点"} and not group["battlefield_rows"]:
            if original_key[1] in claim_keys_with_quantified_battlefields:
                continue
            category = "待激活卖点"
            group["category"] = category
        key = (category, original_key[1])
        if key not in merged:
            merged[key] = group
            continue
        existing = merged[key]
        existing["battlefield_rows"].extend(group["battlefield_rows"])
        for battlefield in group["battlefields"]:
            if battlefield not in existing["battlefields"]:
                existing["battlefields"].append(battlefield)
    for group in merged.values():
        group["battlefield_rows"] = _dedupe_claim_value_cli_battlefield_rows(group["battlefield_rows"])
        group["battlefields"] = []
        for row in group["battlefield_rows"]:
            battlefield = str(row.get("context_name") or row.get("context_code") or "").strip()
            if battlefield and battlefield not in group["battlefields"]:
                group["battlefields"].append(battlefield)
        quant_groups = _claim_value_cli_quant_groups(group["battlefield_rows"])
        group["quant_groups"] = quant_groups
        group["price_total"] = Decimal("0")
        group["sales_total"] = Decimal("0")
        for item in quant_groups:
            row = item.get("representative") or {}
            sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
            group["price_total"] += _decimal(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")) or Decimal("0")
            group["sales_total"] += _decimal(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")) or Decimal("0")
    order = {category: index for index, category in enumerate(_claim_value_cli_category_order())}
    return sorted(merged.values(), key=lambda item: (order.get(str(item.get("category") or ""), 99), str(item.get("claim_name") or "")))


def _dedupe_claim_value_cli_battlefield_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_context: dict[str, dict[str, Any]] = {}
    for row in rows:
        context_key = str(row.get("context_code") or row.get("context_name") or "")
        if not context_key:
            context_key = f"context-{len(best_by_context)}"
        existing = best_by_context.get(context_key)
        if existing is None or _claim_value_cli_row_rank(row) > _claim_value_cli_row_rank(existing):
            best_by_context[context_key] = row
    return list(best_by_context.values())


def _claim_value_cli_row_rank(row: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
    return (
        _decimal(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")) or Decimal("0"),
        _decimal(sku_excess.get("sku_excess_weekly_sales_amount_explained_abs") or sku_excess.get("weekly_sales_amount_lift_abs")) or Decimal("0"),
        _decimal(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")) or Decimal("0"),
        _decimal(row.get("attribution_confidence")) or Decimal("0"),
    )


def _claim_value_cli_category(row: dict[str, Any]) -> str:
    label = str(row.get("business_claim_type_cn") or _claim_role_cn(row.get("claim_value_role")))
    if label in {"高溢价卖点", "份额转化卖点", "客户获得价值卖点", "门槛卖点"} and _claim_value_cli_has_weak_sample_flag(row):
        return "待激活卖点" if _claim_value_cli_has_strong_fact_evidence(row) else "样本不足待复核"
    if label == "样本不足待复核" and _claim_value_cli_has_strong_fact_evidence(row):
        return "待激活卖点"
    return label


def _claim_value_cli_has_weak_sample_flag(row: dict[str, Any]) -> bool:
    flags = {str(item) for item in (row.get("quality_flags") or row.get("quality_flags_json") or [])}
    return bool(flags & {"insufficient_comparison_group", "sample_weak", "sample_insufficient"})


def _claim_value_cli_quant_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    order: list[tuple[str, ...]] = []
    for row in rows:
        signature = _claim_value_cli_quant_signature(row)
        if signature is None:
            signature = (
                str(row.get("claim_code") or row.get("claim_name") or "claim"),
                str(row.get("context_code") or row.get("context_name") or len(order)),
            )
        if signature not in grouped:
            grouped[signature] = {"rows": [], "battlefields": []}
            order.append(signature)
        item = grouped[signature]
        item["rows"].append(row)
        battlefield = str(row.get("context_name") or row.get("context_code") or "").strip()
        if battlefield and battlefield not in item["battlefields"]:
            item["battlefields"].append(battlefield)
    result: list[dict[str, Any]] = []
    for signature in order:
        item = grouped[signature]
        item["representative"] = item["rows"][0] if item["rows"] else {}
        result.append(item)
    return result


def _claim_value_cli_quant_signature(row: dict[str, Any]) -> tuple[str, ...] | None:
    pool = row.get("pool_effect") or {}
    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
    metric_keys = (
        _claim_value_cli_metric_key(pool.get("pool_claim_price_delta_abs")),
        _claim_value_cli_metric_key(pool.get("pool_claim_weekly_sales_delta_abs")),
        _claim_value_cli_metric_key(pool.get("pool_claim_weekly_sales_amount_delta_abs")),
        _claim_value_cli_metric_key(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")),
        _claim_value_cli_metric_key(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")),
        _claim_value_cli_metric_key(sku_excess.get("sku_excess_weekly_sales_amount_explained_abs") or sku_excess.get("weekly_sales_amount_lift_abs")),
    )
    if not any(metric_keys):
        return None
    return (
        str(row.get("business_claim_type_cn") or _claim_role_cn(row.get("claim_value_role"))),
        str(row.get("size_tier") or ""),
        str(row.get("price_band_group") or ""),
        *metric_keys,
    )


def _claim_value_cli_metric_key(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return str(number.quantize(Decimal("0.0001")))


def _claim_value_cli_has_strong_fact_evidence(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence_strength") or {}
    values = [_decimal(evidence.get(key)) for key in ("claim", "param", "comment")]
    values = [value for value in values if value is not None]
    return bool(values) and sum(1 for value in values if value >= Decimal("0.75")) >= 2


def _dedupe_claim_value_cli_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("claim_code") or row.get("claim_name") or "")
        if not key:
            key = f"claim-{len(deduped)}"
        context = str(row.get("context_name") or row.get("context_code") or "").strip()
        if key not in deduped:
            item = dict(row)
            item["market_contexts"] = [context] if context else []
            deduped[key] = item
            continue
        contexts = deduped[key].setdefault("market_contexts", [])
        if context and context not in contexts:
            contexts.append(context)
    return list(deduped.values())


def _format_claim_contribution_text(result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    payload = ((result.get("result") or {}).get("claim_contribution") or {})
    rows = payload.get("attributions") or []
    if not rows:
        return result.get("message_cn") or "当前 SKU 没有 M12C 卖点商业价值分析结果。"
    lines = [f"{_brand_model(target)} 的卖点商业价值分析："]
    for row in rows[:8]:
        gap = row.get("sku_gap_vs_baseline") or {}
        positives = row.get("positive_claims") or []
        names = "、".join(str(item.get("claim_name") or item.get("claim_code")) for item in positives[:4]) or "未形成高置信正向卖点"
        lines.append(
            f"- {row.get('context_name') or row.get('context_code')}：{names}；"
            f"相对可比产品基准价格差约{_format_money(gap.get('price_premium_abs')) or '0元'}；"
            f"周均销量差约{_format_volume(gap.get('weekly_sales_lift_abs')) or '0'}台。"
        )
    lines.append("说明：该结果用于解释本品相对可比产品基准的可观测表现差异，不可直接视为因果增量。")
    return "\n".join(lines)


def _format_claim_value_space_text(result: dict[str, Any]) -> str:
    payload = ((result.get("result") or {}).get("claim_value_space") or {})
    rows = payload.get("items") or []
    if not rows:
        return result.get("message_cn") or "当前没有匹配的 M12C 卖点价值空间结果。"
    lines = ["卖点价值空间："]
    for row in rows[:10]:
        roles = row.get("role_counts") or {}
        space = row.get("market_space") or {}
        lines.append(
            f"- {row.get('claim_name') or row.get('claim_code')} × {row.get('dimension_name') or row.get('dimension_code')} "
            f"({row.get('size_tier')}/{row.get('price_band_group')})：覆盖 {row.get('sku_count')} 个 SKU；"
            f"溢价 {roles.get('premium_driver_estimated', 0)} 个，销量 {roles.get('sales_driver_estimated', 0)} 个；"
            f"空间周均销量约{_format_volume(space.get('estimated_avg_weekly_sales_volume')) or '0'}台。"
        )
    return "\n".join(lines)


def _select_key_competitors(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    close_price = [
        item
        for item in candidates
        if (_abs_decimal(((item.get("candidate") or {}).get("price_gap_pct_to_target"))) or Decimal("0")) <= Decimal("0.15")
    ]
    selected: list[dict[str, Any]] = sorted(close_price, key=_competitor_business_score, reverse=True)[:2]
    if candidates:
        price_adjacent = min(
            candidates,
            key=lambda item: _abs_decimal(((item.get("candidate") or {}).get("price_gap_pct_to_target"))) or Decimal("999"),
        )
        if price_adjacent not in selected:
            selected.append(price_adjacent)
    for item in sorted(candidates, key=_competitor_business_score, reverse=True):
        if len(selected) >= 3:
            break
        if item not in selected:
            selected.append(item)
    return selected[:3]


def _format_competitor_line(item: dict[str, Any]) -> str:
    cand = item.get("candidate") or {}
    basis = item.get("basis") or {}
    name = _brand_model(cand)
    role = _competitor_role(item)
    price_text = _format_money(cand.get("price_wavg"))
    price_gap = _format_price_gap(cand.get("price_gap_pct_to_target"), cand.get("price_gap_to_target"))
    sales_text = _format_volume(cand.get("avg_weekly_sales_volume"))
    semantic = _format_percent(basis.get("semantic_overlap_score"))
    param = _format_percent(basis.get("param_claim_overlap_score"))
    sales_closeness = _format_percent(basis.get("sales_closeness_score"))

    facts: list[str] = [role]
    if price_text:
        facts.append(f"均价约{price_text}")
    if price_gap:
        facts.append(price_gap)
    if semantic:
        facts.append(f"需求重合度约{semantic}")
    if param:
        facts.append(f"参数卖点重合度约{param}")
    if sales_closeness:
        facts.append(f"销量接近度约{sales_closeness}")
    if sales_text:
        facts.append(f"周均销量约{sales_text}台")
    return f"{name}：{'；'.join(facts)}。"


def _competitor_business_score(item: dict[str, Any]) -> Decimal:
    basis = item.get("basis") or {}
    cand = item.get("candidate") or {}
    semantic = _decimal(basis.get("semantic_overlap_score")) or Decimal("0")
    param = _decimal(basis.get("param_claim_overlap_score")) or Decimal("0")
    sales = _decimal(basis.get("sales_closeness_score")) or Decimal("0")
    price_gap = _abs_decimal(cand.get("price_gap_pct_to_target")) or Decimal("1")
    price = max(Decimal("0"), Decimal("1") - min(price_gap, Decimal("1")))
    return semantic * Decimal("0.45") + param * Decimal("0.25") + sales * Decimal("0.20") + price * Decimal("0.10")


def _competitor_role(item: dict[str, Any]) -> str:
    cand = item.get("candidate") or {}
    basis = item.get("basis") or {}
    gap = _decimal(cand.get("price_gap_pct_to_target"))
    semantic = _decimal(basis.get("semantic_overlap_score")) or Decimal("0")
    if gap is not None and gap <= Decimal("-0.15"):
        return "下探分流竞品"
    if gap is not None and gap >= Decimal("0.15"):
        return "上探替代竞品"
    if gap is not None and abs(gap) <= Decimal("0.03"):
        return "价格贴身竞品"
    if semantic >= Decimal("0.80"):
        return "最直接竞品"
    return "同尺寸同价位竞品"


def _brand_model(payload: dict[str, Any]) -> str:
    brand = str(payload.get("brand_name") or "").strip()
    model = str(payload.get("model_name") or payload.get("sku_code") or "").strip()
    if brand and model:
        return f"{brand} {model}"
    return brand or model or "该 SKU"


def _price_band_cn(value: Any) -> str:
    mapping = {
        "low": "低价位段",
        "mid_low": "中低价位段",
        "mid": "中价位段",
        "mid_high": "中高价位段",
        "high": "高价位段",
    }
    return mapping.get(str(value or "").lower(), "")


def _claim_role_cn(value: Any) -> str:
    mapping = {
        "premium_driver_estimated": "高溢价卖点",
        "sales_driver_estimated": "份额转化卖点",
        "basic_threshold": "门槛卖点",
        "value_bundle_claim": "客户获得价值卖点",
        "weak_user_perception_claim": "待激活卖点",
        "high_price_competitor_intercept": "竞品拦截卖点",
        "price_up_opportunity": "竞品拦截卖点",
        "user_validated_need": "待激活卖点",
        "brand_claim_only": "厂家主张卖点",
        "opportunity_gap": "竞品拦截卖点",
        "drag_factor": "价格压力卖点",
        "sample_insufficient": "样本不足待复核",
    }
    return mapping.get(str(value or ""), str(value or "未分类"))


def _format_money(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{number.quantize(Decimal('1')):,}元"


def _format_volume(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    if number == number.to_integral_value():
        return f"{number.quantize(Decimal('1')):,}"
    rounded = number.quantize(Decimal("0.1"))
    if rounded == rounded.to_integral_value():
        return f"{rounded.quantize(Decimal('1')):,}"
    return f"{rounded:,}"


def _format_number(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    if number == number.to_integral_value():
        return f"{number.quantize(Decimal('1'))}"
    return f"{number.normalize()}"


def _format_percent(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{(number * Decimal('100')).quantize(Decimal('1'))}%"


def _format_price_gap(gap_pct: Any, gap_amount: Any = None) -> str:
    pct = _decimal(gap_pct)
    amount = _decimal(gap_amount)
    if pct is None:
        return ""
    direction = "便宜" if pct < 0 else "贵" if pct > 0 else "几乎同价"
    if direction == "几乎同价":
        return direction
    pct_text = _format_percent(abs(pct))
    if amount is not None:
        amount_text = _format_money(abs(amount))
        return f"比目标{direction}约{pct_text}（约{amount_text}）"
    return f"比目标{direction}约{pct_text}"


def _pair_price_gap_text(target: dict[str, Any], candidate: dict[str, Any]) -> str:
    target_price = _decimal(target.get("weighted_price") or target.get("price_wavg"))
    candidate_price = _decimal(candidate.get("weighted_price") or candidate.get("price_wavg"))
    if target_price is None or candidate_price is None or target_price == 0:
        return ""
    gap = (candidate_price - target_price) / target_price
    return _format_price_gap(gap, candidate_price - target_price)


def _sales_lead_text(
    target_name: str,
    candidate_name: str,
    volume_gap: Decimal | None,
    volume_ratio: Decimal | None,
) -> str:
    if volume_gap is None:
        return ""
    gap = _format_volume(abs(volume_gap))
    ratio_text = _format_ratio(volume_ratio) if volume_ratio is not None else ""
    if volume_gap > 0:
        suffix = f"，约为对方的 {ratio_text}" if ratio_text else ""
        return f"{target_name} 比 {candidate_name} 高约 {gap} 台/周{suffix}"
    if volume_gap < 0:
        suffix = f"，约为对方的 {ratio_text}" if ratio_text else ""
        return f"{candidate_name} 比 {target_name} 高约 {gap} 台/周{suffix}"
    return "两款产品周均销量基本持平"


def _format_ratio(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{number.quantize(Decimal('0.01'))} 倍"


CLAIM_LABELS_CN = {
    "tv_claim_ai_large_model": "AI 大模型/智能能力",
    "tv_claim_casting_connectivity": "投屏互联",
    "tv_claim_chip_performance": "芯片性能",
    "tv_claim_dolby_audio_video": "杜比音画",
    "tv_claim_eye_care_display": "护眼显示",
    "tv_claim_flush_wall_mount": "贴墙/超薄外观",
    "tv_claim_gaming_low_latency": "游戏低延迟",
    "tv_claim_hdmi21_connectivity": "HDMI 2.1 连接",
    "tv_claim_hdr_high_brightness": "高亮度 HDR",
    "tv_claim_high_refresh_rate": "高刷新率",
    "tv_claim_local_dimming": "分区控光",
    "tv_claim_memory_storage": "内存/存储",
    "tv_claim_miniled_display": "MiniLED 显示",
    "tv_claim_oled_self_lit": "OLED 自发光",
    "tv_claim_picture_engine_ai": "AI 画质引擎",
    "tv_claim_qd_miniled_display": "量子点 MiniLED",
    "tv_claim_rgb_miniled_display": "RGB MiniLED",
    "tv_claim_smart_home_iot": "智能家居互联",
    "tv_claim_theater_scene": "影院音画体验",
    "tv_claim_voice_control": "语音控制",
    "tv_claim_wide_color_accuracy": "广色域/色彩还原",
}


def _claim_names(codes: list[Any]) -> list[str]:
    names: list[str] = []
    for code in codes:
        label = CLAIM_LABELS_CN.get(str(code), "")
        if label and label not in names:
            names.append(label)
    return names


def _sanitize_business_limitation(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "M01" in text or "M07" in text:
        return "部分候选缺少完整重叠在售周明细，已使用当前市场画像周均表现作为参考。"
    for token in ("M03B", "M04C", "M05C", "M09C", "M10C", "M11C", "M11D"):
        text = text.replace(token, "对应分析层")
    return text


def _abs_decimal(value: Any) -> Decimal | None:
    number = _decimal(value)
    return abs(number) if number is not None else None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _clean_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value not in (None, "")}


if __name__ == "__main__":
    sys.exit(main())
