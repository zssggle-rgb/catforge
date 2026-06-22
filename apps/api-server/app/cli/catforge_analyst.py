"""Agent-facing CatForge analyst CLI framework.

The CLI is intentionally a thin adapter over ``CatForgeAnalystService``. It
provides stable command names, shared context arguments, and deterministic JSON
output so OpenClaw/Claude Code skills can compose atomic abilities and SOPs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
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
                limit=getattr(args, "limit", DEFAULT_CANDIDATE_LIMIT),
            )
    except CatForgeAnalystError as exc:
        result = {
            "status": AnalystStatus.ERROR.value,
            "command": getattr(args, "command", None),
            "message_cn": str(exc),
            "error": str(exc),
        }
        emit_result(result, args.format)
        return 1

    emit_result(result, args.format)
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
        add_format_arg(command_parser)

    for command in SOP_COMMAND_ORDER:
        command_parser = subparsers.add_parser(command, help=f"Run analyst SOP: {command}.")
        add_context_args(command_parser)
        add_sku_args(command_parser)
        add_pair_args(command_parser)
        add_dimension_args(command_parser)
        command_parser.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
        add_format_arg(command_parser)

    ask = subparsers.add_parser("ask", help="Route a natural-language analyst question to an atom or SOP.")
    add_context_args(ask)
    add_sku_args(ask)
    add_pair_args(ask)
    add_dimension_args(ask)
    ask.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
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
    parser.add_argument("--dimension-type", choices=("user_task", "target_group", "battlefield"), help="Semantic dimension type.")
    parser.add_argument("--dimension-code", help="Semantic dimension code, such as BF_LARGE_SCREEN_VALUE_UPGRADE.")
    parser.add_argument("--brand-name", help="Optional brand filter for dimension-space commands.")
    parser.add_argument("--size-tier", help="Optional five-tier size filter.")
    parser.add_argument("--price-band", help="Optional size-tier price band filter.")
    parser.add_argument("--claim-code", help="Optional claim code filter for comment-support.")
    parser.add_argument("--param-code", help="Optional param code filter for comment-support.")
    parser.add_argument("--user-task-code", help="Optional user task code filter for comment-support.")
    parser.add_argument("--target-group-code", help="Optional target group code filter for comment-support.")
    parser.add_argument("--battlefield-code", help="Optional battlefield code filter for comment-support.")


def add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="json")


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
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    candidate_sku_code: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="ask",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=product_category,
        question=question,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
        candidate_sku_code=candidate_sku_code,
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


def emit_result(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, default=json_default, indent=2, sort_keys=True))
        return
    message = result.get("message_cn")
    if message:
        print(message)
    outline = result.get("answer_outline") or []
    for item in outline:
        print(f"- {item}")
    if not message and not outline:
        print(json.dumps(result, ensure_ascii=False, default=json_default, indent=2, sort_keys=True))


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _clean_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value not in (None, "")}


if __name__ == "__main__":
    sys.exit(main())
