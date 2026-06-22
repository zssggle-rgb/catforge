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
    limit: int = DEFAULT_CANDIDATE_LIMIT,
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
        limit=limit,
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


def format_business_text(result: dict[str, Any]) -> str:
    payload = result.get("result") or {}
    if "competitor_set" in payload:
        return _format_competitor_set_text(result)
    if "why_sales_diff" in payload:
        return _format_why_sales_diff_text(result)
    return ""


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
    limitations = [item for item in result.get("limitations") or [] if item]
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
    limitations = [item for item in result.get("limitations") or [] if item]
    if limitations:
        lines.append(f"补充限制：{'；'.join(str(item) for item in limitations[:3])}。")
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
