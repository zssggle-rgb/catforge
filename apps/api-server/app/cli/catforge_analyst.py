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
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.core3_real_data.analyst import competitor_answer as competitor_answer_renderer
from app.services.core3_real_data.analyst.analyst_repository import (
    batch_ids_from_scope,
)
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext, AnalystStatus, base_result
from app.services.core3_real_data.analyst.analyst_service import (
    ATOM_COMMANDS,
    LATEST_BATCH,
    SOP_COMMANDS,
    CatForgeAnalystError,
    CatForgeAnalystService,
    route_question,
)
from app.services.core3_real_data.analyst.competitor_profile_consumption import (
    CompetitorProfileConsumptionService,
)
from app.services.core3_real_data.analyst.competitor_profile_generation import (
    CompetitorProfileGenerationAlreadyRunningError,
    CompetitorProfileGenerationReadbackError,
    CompetitorProfileGenerationService,
)
from app.services.core3_real_data.analyst.competitor_profile_generation_schemas import (
    CompetitorProfileGenerationRequest,
)
from app.services.core3_real_data.analyst.competitor_profile_input_provider import (
    CompetitorProfileInputError,
    CompetitorProfileInputProvider,
)
from app.services.core3_real_data.analyst.competitor_profile_presentation import (
    build_competitor_profile_presentation,
)
from app.services.core3_real_data.analyst.competitor_profile_reader import (
    CompetitorProfileReader,
)
from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileReadRequest,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileRepository,
    CompetitorProfileRepositoryError,
)
from app.services.core3_real_data.analyst.competitor_profile_request_builder import (
    build_production_generation_request,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_generation import (
    CompetitorProfileAgentSnapshotGenerationService,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_input_provider import (
    AnalystSellpointValueMaterializationInputProvider,
    SellpointValueProfileInputError,
    build_production_version_request,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_lifecycle import (
    SellpointValueGenerationAlreadyRunningError,
    SellpointValueProfileLifecycleService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
    SellpointValueProfileRepositoryError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorProfileAdapter,
    SellpointValueCompetitorSourceIntegrityError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SellpointValueV51GenerationAlreadyRunningError,
    SellpointValueV51GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_input_provider import (
    SavedV5SellpointValueV51InputProvider,
    SellpointValueV51ProductionInputError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_repository import (
    SellpointValueV51Repository,
    SellpointValueV51RepositoryError,
)
from app.services.core3_real_data.constants import (
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.repositories import (
    Core3RepositoryContext,
)
from app.services.core3_real_data.purchase_reason_profile_preview import (
    M12DSkuPurchaseReasonPreviewError,
    build_sku_purchase_reason_preview,
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
    "sellpoint-value-evidence",
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
    "sellpoint-value-profile-ask",
    "sellpoint-value-pm-v5",
    "sellpoint-value-pm-v4",
    "sellpoint-value-pm",
    "competitor-set",
    "why-sales-diff",
    "premium-claim-drivers",
    "battlefield-space",
    "battlefield-opportunity",
    "low-sales-diagnosis",
    "sku-business-brief",
)

PROFILE_WRITE_COMMANDS = (
    "competitor-profile-batch-generate",
    "competitor-profile-generate",
    "competitor-profile-v1-1-generate",
    "sellpoint-value-profile-generate",
    "sellpoint-value-profile-batch-generate",
    "sellpoint-value-profile-v5-1-generate",
)

COMPETITOR_PROFILE_WRITE_COMMANDS = (
    "competitor-profile-batch-generate",
    "competitor-profile-generate",
    "competitor-profile-v1-1-generate",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "sellpoint-value-pm-v5" and not getattr(args, "enable_v5", False):
        result = {
            "status": AnalystStatus.ERROR.value,
            "command": args.command,
            "message_cn": "用户卖点价值 V5 默认关闭；请显式传入 --enable-v5。",
        }
        emit_result(result, args.format)
        return 1
    if args.command == "sellpoint-value-pm-v4" and not getattr(args, "enable_v4", False):
        result = {
            "status": AnalystStatus.ERROR.value,
            "command": args.command,
            "message_cn": "用户卖点价值 V4 默认关闭；请显式传入 --enable-v4。",
        }
        emit_result(result, args.format)
        return 1
    if args.command in PROFILE_WRITE_COMMANDS and not getattr(
        args, "enable_profile_write", False
    ):
        result = {
            "status": AnalystStatus.ERROR.value,
            "command": args.command,
            "message_cn": "画像草稿写入默认关闭；请显式传入 --enable-profile-write。",
        }
        emit_result(result, args.format)
        return 1
    try:
        with SessionLocal() as db:
            if args.command == "competitor-profile-v1-1-generate":
                result = run_competitor_profile_v1_1_generation(db, args)
            elif args.command in COMPETITOR_PROFILE_WRITE_COMMANDS:
                result = run_competitor_profile_generation(db, args)
            elif args.command == "competitor-profile-build-request":
                result = run_competitor_profile_build_request(db, args)
            elif args.command == "competitor-profile-preview":
                result = run_competitor_profile_preview(db, args)
            elif args.command == "competitor-profile-read":
                result = run_competitor_profile_read(db, args)
            elif args.command == "sellpoint-value-profile-v5-1-generate":
                result = run_sellpoint_value_profile_v5_1_generation(db, args)
            elif args.command in PROFILE_WRITE_COMMANDS:
                result = run_sellpoint_value_profile_generation(db, args)
            elif args.command == "sku-purchase-reason":
                result = sku_purchase_reason(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=args.product_category,
                    market_window=args.market_window,
                    analysis_population=args.analysis_population,
                    query=getattr(args, "query", None),
                    sku_code=getattr(args, "sku_code", None),
                    model_name=getattr(args, "model_name", None),
                    taxonomy_version=args.taxonomy_version,
                    max_anchors=args.max_anchors,
                )
            else:
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
                    question=(
                        getattr(args, "profile_question", None)
                        or " ".join(getattr(args, "question", ()) or ())
                    ),
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
                    enable_v5=getattr(args, "enable_v5", False),
                    enable_v4=getattr(args, "enable_v4", False),
                    selection_compare_url=getattr(args, "selection_compare_url", None),
                    evidence_report_url=getattr(args, "evidence_report_url", None),
                    preview_profile_version=getattr(
                        args, "preview_profile_version", None
                    ),
                    preview_sellpoint_value_profile_version_id=getattr(
                        args,
                        "preview_sellpoint_value_profile_version_id",
                        None,
                    ),
                    profile_version=getattr(args, "profile_version", None),
                    sellpoint_value_profile_version_id=getattr(
                        args,
                        "sellpoint_value_profile_version_id",
                        None,
                    ),
                    expected_result_hash=getattr(
                        args, "expected_result_hash", None
                    ),
                    topic_code=getattr(args, "qa_topic", None),
                    compare_profile_version=getattr(
                        args, "compare_profile_version", None
                    ),
                    profile_access_mode=getattr(
                        args, "profile_access_mode", None
                    ),
                    competitor_profile_version_id=getattr(
                        args, "competitor_profile_version_id", None
                    ),
                    competitor_profile_release_scope_key=getattr(
                        args, "competitor_profile_release_scope_key", None
                    ),
                    allow_draft_preview=getattr(
                        args, "allow_competitor_profile_draft_preview", False
                    ),
                    legacy_live_analysis=getattr(
                        args, "legacy_competitor_live_analysis", False
                    ),
                )
                attach_feishu_card_delivery(result, args)
    except (
        CatForgeAnalystError,
        M12DSkuPurchaseReasonPreviewError,
        SellpointValueGenerationAlreadyRunningError,
        SellpointValueProfileInputError,
        SellpointValueProfileRepositoryError,
        SellpointValueV51GenerationAlreadyRunningError,
        SellpointValueV51ProductionInputError,
        SellpointValueV51RepositoryError,
        SellpointValueCompetitorSourceIntegrityError,
        CompetitorProfileGenerationAlreadyRunningError,
        CompetitorProfileGenerationReadbackError,
        CompetitorProfileInputError,
        CompetitorProfileRepositoryError,
        ValueError,
    ) as exc:
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

    purchase_reason = subparsers.add_parser(
        "sku-purchase-reason",
        help="Preview one SKU's M12D purchase reason profile.",
    )
    add_context_args(purchase_reason)
    add_sku_args(purchase_reason)
    purchase_reason.add_argument(
        "--taxonomy-version",
        help="M12D purchase reason anchor taxonomy version. Defaults by product category.",
    )
    purchase_reason.add_argument("--max-anchors", type=int, default=8)
    purchase_reason.add_argument("--format", choices=("json", "markdown"), default="json")

    profile_generate = subparsers.add_parser(
        "sellpoint-value-profile-generate",
        help="Generate and persist one immutable sellpoint-value profile draft.",
    )
    add_profile_generation_args(profile_generate, batch=False)

    profile_batch = subparsers.add_parser(
        "sellpoint-value-profile-batch-generate",
        help="Generate drafts for the complete authoritative SKU scope.",
    )
    add_profile_generation_args(profile_batch, batch=True)

    profile_v5_1_generate = subparsers.add_parser(
        "sellpoint-value-profile-v5-1-generate",
        help=(
            "Generate one immutable V5.1 draft from an explicit saved V5 profile "
            "and the formal current competitor-agent snapshot."
        ),
    )
    profile_v5_1_generate.add_argument("--project-id", required=True)
    profile_v5_1_generate.add_argument(
        "--category-code", choices=("TV", "AC"), required=True
    )
    profile_v5_1_generate.add_argument("--batch-id", required=True)
    profile_v5_1_generate.add_argument("--sku-code", required=True)
    profile_v5_1_generate.add_argument("--profile-version", required=True)
    profile_v5_1_generate.add_argument("--source-profile-version", required=True)
    profile_v5_1_generate.add_argument("--generated-by", required=True)
    profile_v5_1_generate.add_argument(
        "--result-detail",
        choices=("summary", "full"),
        default="summary",
    )
    profile_v5_1_generate.add_argument(
        "--enable-profile-write",
        action="store_true",
        help="Explicitly allow this single-SKU immutable V5.1 draft write.",
    )
    add_format_arg(profile_v5_1_generate)

    competitor_profile_generate = subparsers.add_parser(
        "competitor-profile-generate",
        help="Generate and persist one competitor-profile draft from a typed request.",
    )
    add_competitor_profile_generation_args(competitor_profile_generate, batch=False)

    competitor_profile_batch = subparsers.add_parser(
        "competitor-profile-batch-generate",
        help="Generate competitor-profile drafts for one authoritative category scope.",
    )
    add_competitor_profile_generation_args(competitor_profile_batch, batch=True)

    competitor_profile_v11_generate = subparsers.add_parser(
        "competitor-profile-v1-1-generate",
        help="Generate and persist one production V1.1 competitor-profile draft.",
    )
    competitor_profile_v11_generate.add_argument("--project-id", required=True)
    competitor_profile_v11_generate.add_argument(
        "--category-code", choices=("TV", "AC"), required=True
    )
    competitor_profile_v11_generate.add_argument("--sku-code", required=True)
    competitor_profile_v11_generate.add_argument("--profile-version", required=True)
    competitor_profile_v11_generate.add_argument("--generated-by", required=True)
    competitor_profile_v11_generate.add_argument(
        "--enable-profile-write",
        action="store_true",
        help="Explicitly allow this immutable V1.1 draft write.",
    )
    add_format_arg(competitor_profile_v11_generate)

    competitor_profile_request = subparsers.add_parser(
        "competitor-profile-build-request",
        help="Build a typed generation request from one current published category scope.",
    )
    competitor_profile_request.add_argument("--project-id", required=True)
    competitor_profile_request.add_argument(
        "--category-code", choices=("TV", "AC"), required=True
    )
    competitor_profile_request.add_argument("--profile-version", required=True)
    competitor_profile_request.add_argument("--generated-by", required=True)
    add_format_arg(competitor_profile_request)

    competitor_profile_read = subparsers.add_parser(
        "competitor-profile-read",
        help="Read one formal current profile or one explicitly selected draft preview.",
    )
    competitor_profile_read.add_argument("--project-id", required=True)
    competitor_profile_read.add_argument(
        "--category-code", choices=("TV", "AC"), required=True
    )
    competitor_profile_read.add_argument("--release-scope-key", required=True)
    competitor_profile_read.add_argument("--sku-code", required=True)
    competitor_profile_read.add_argument(
        "--mode", choices=("formal", "preview"), default="formal"
    )
    competitor_profile_read.add_argument("--competitor-profile-version-id")
    competitor_profile_read.add_argument(
        "--allow-draft-preview",
        action="store_true",
        help="Explicitly allow the selected draft only for development acceptance.",
    )
    add_format_arg(competitor_profile_read)

    competitor_profile_preview = subparsers.add_parser(
        "competitor-profile-preview",
        help="Render card, reports, QA, and sellpoint handoff from one saved profile.",
    )
    competitor_profile_preview.add_argument("--project-id", required=True)
    competitor_profile_preview.add_argument(
        "--category-code", choices=("TV", "AC"), required=True
    )
    competitor_profile_preview.add_argument("--release-scope-key", required=True)
    competitor_profile_preview.add_argument("--sku-code", required=True)
    competitor_profile_preview.add_argument(
        "--mode", choices=("formal", "preview"), default="formal"
    )
    competitor_profile_preview.add_argument("--competitor-profile-version-id")
    competitor_profile_preview.add_argument(
        "--allow-draft-preview",
        action="store_true",
        help="Explicitly allow the selected draft only for development acceptance.",
    )
    competitor_profile_preview.add_argument(
        "--with-report",
        choices=("none", "markdown", "feishu-doc"),
        default="none",
    )
    add_format_arg(competitor_profile_preview)

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
        if command == "competitor-set":
            add_competitor_profile_agent_args(command_parser)
        if command == "sellpoint-value-profile-ask":
            command_parser.add_argument(
                "--question",
                dest="profile_question",
                required=True,
                help="Product-manager question answered from one stored profile.",
            )
            command_parser.add_argument("--profile-version")
            command_parser.add_argument(
                "--profile-access-mode",
                choices=("formal", "preview"),
                default="formal",
            )
            command_parser.add_argument(
                "--sellpoint-value-profile-version-id"
            )
            command_parser.add_argument("--expected-result-hash")
            command_parser.add_argument("--qa-topic")
            command_parser.add_argument("--compare-profile-version")
        if command == "sellpoint-value-pm-v5":
            command_parser.add_argument(
                "--enable-v5",
                action="store_true",
                help="Explicitly enable the default-off V5 analysis for this invocation.",
            )
            command_parser.add_argument("--selection-compare-url")
            command_parser.add_argument("--evidence-report-url")
            command_parser.add_argument(
                "--preview-profile-version",
                help=(
                    "Explicitly preview one saved profile version. Without this "
                    "flag V5 only reads the current published profile."
                ),
            )
            command_parser.add_argument(
                "--preview-sellpoint-value-profile-version-id",
                help="Lock preview to one immutable V5.1 version id.",
            )
        if command == "sellpoint-value-pm-v4":
            command_parser.add_argument(
                "--enable-v4",
                action="store_true",
                help="Explicitly enable the default-off V4 analysis for this invocation.",
            )
            command_parser.add_argument("--selection-compare-url")
            command_parser.add_argument("--evidence-report-url")
        add_format_arg(command_parser)

    ask = subparsers.add_parser("ask", help="Route a natural-language analyst question to an atom or SOP.")
    add_context_args(ask)
    add_sku_args(ask)
    add_pair_args(ask)
    add_dimension_args(ask)
    ask.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    add_answer_args(ask)
    add_competitor_profile_agent_args(ask)
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


def add_profile_generation_args(
    parser: argparse.ArgumentParser,
    *,
    batch: bool,
) -> None:
    add_context_args(parser)
    if not batch:
        parser.add_argument(
            "--sku-code",
            required=True,
            help="Exact authoritative SKU code to materialize.",
        )
    parser.add_argument("--profile-version", required=True)
    parser.add_argument("--m12d-profile-version")
    parser.add_argument("--generated-by", required=True)
    parser.add_argument(
        "--enable-profile-write",
        action="store_true",
        help="Explicitly allow draft-only profile writes for this invocation.",
    )
    if batch:
        parser.add_argument("--page-size", type=int, default=50)
        parser.add_argument(
            "--max-new-skus",
            type=int,
            help=(
                "Bound unfinished SKU generation in this process. Relaunch with "
                "the default resume mode to continue from the next checkpoint."
            ),
        )
        parser.add_argument(
            "--regenerate-existing",
            action="store_true",
            help="Re-read existing immutable drafts instead of resuming unfinished SKUs only.",
        )
    add_format_arg(parser)


def add_competitor_profile_generation_args(
    parser: argparse.ArgumentParser,
    *,
    batch: bool,
) -> None:
    parser.add_argument(
        "--request-json",
        required=True,
        help=(
            "Path to a CompetitorProfileGenerationRequest JSON document, or '-' "
            "to read it from stdin."
        ),
    )
    if not batch:
        parser.add_argument("--sku-code", required=True)
        parser.add_argument(
            "--result-detail",
            choices=("summary", "full"),
            default="summary",
            help=(
                "Return an operational summary by default; use full only for "
                "small local fixtures."
            ),
        )
    parser.add_argument(
        "--enable-profile-write",
        action="store_true",
        help="Explicitly allow draft-only profile writes for this invocation.",
    )
    if batch:
        parser.add_argument("--page-size", type=int, default=50)
        parser.add_argument("--max-new-skus", type=int)
        parser.add_argument(
            "--regenerate-existing",
            action="store_true",
            help="Re-read existing immutable drafts instead of resuming unfinished SKUs only.",
        )
    add_format_arg(parser)


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
    parser.add_argument("--feishu-chat-id", help="Feishu chat_id or direct user open_id to send the generated card in the main chat.")
    parser.add_argument("--feishu-reply-message-id", help="Feishu message_id to reply with the generated competitor card.")
    parser.add_argument("--feishu-reply-in-thread", action="store_true", help="Send the Feishu card as a thread reply.")
    parser.add_argument("--feishu-card-idempotency-key", help="Optional idempotency key for Feishu card reply.")
    parser.add_argument("--feishu-card-only", action="store_true", help="For text output, print only Feishu card delivery status.")


def add_competitor_profile_agent_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--competitor-profile-mode",
        dest="profile_access_mode",
        choices=("formal", "preview"),
        default="formal",
        help="Read current published V1.1 by default, or explicitly preview one draft.",
    )
    parser.add_argument("--competitor-profile-version-id")
    parser.add_argument("--competitor-profile-release-scope-key")
    parser.add_argument(
        "--allow-competitor-profile-draft-preview",
        action="store_true",
        help="Explicitly opt in to the selected V1.1 draft preview.",
    )
    parser.add_argument(
        "--legacy-competitor-live-analysis",
        action="store_true",
        help="Operations-only fallback to the retired live-analysis path.",
    )


def run_competitor_profile_v1_1_generation(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    context = Core3RepositoryContext(
        db=db,
        project_id=args.project_id,
        category_code=Core3CategoryCode(args.category_code),
    )
    result = CompetitorProfileAgentSnapshotGenerationService(
        repository=CompetitorProfileAgentSnapshotRepository(context),
        input_provider=CompetitorProfileInputProvider(context),
    ).generate_single_draft(
        target_sku_code=args.sku_code,
        profile_version=args.profile_version,
        generated_by=args.generated_by,
    )
    profile = result.profile
    return {
        "status": AnalystStatus.OK.value,
        "command": args.command,
        "generation": {
            "status": result.status,
            "competitor_profile_version_id": (
                result.version.competitor_profile_version_id
            ),
            "profile_version": result.version.profile_version,
            "release_scope_key": result.version.release_scope_key,
            "release_status": str(result.version.release_status),
            "is_current": result.version.is_current,
            "processing_status": result.version.processing_status,
            "target_sku_code": profile.target.sku_code,
            "candidate_count": result.candidate_count,
            "selected_sku_codes": list(result.selected_sku_codes),
            "profile_result_hash": profile.result_hash,
            "source_analysis_result_hash": profile.source_analysis_result_hash,
            "candidate_pool_order": profile.candidate_pool_order,
            "analysis_order": profile.analysis_order,
        },
    }


def run_competitor_profile_generation(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    request = _load_competitor_profile_generation_request(args.request_json)
    context = Core3RepositoryContext(
        db=db,
        project_id=request.input_request.project_id,
        category_code=Core3CategoryCode(request.input_request.category_code),
    )
    repository = CompetitorProfileRepository(context)
    service = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=CompetitorProfileInputProvider(context),
    )
    if args.command == "competitor-profile-generate":
        result = service.generate_draft(
            request,
            target_sku_code=str(args.sku_code).strip().upper(),
        )
        return {
            "status": AnalystStatus.OK.value,
            "command": args.command,
            "generation": _competitor_profile_generation_output(
                result,
                detail=getattr(args, "result_detail", "full"),
            ),
        }
    result = service.batch_generate(
        request,
        resume_unfinished_only=not bool(args.regenerate_existing),
        page_size=args.page_size,
        max_new_skus=args.max_new_skus,
    )
    return {
        "status": AnalystStatus.OK.value,
        "command": args.command,
        "generation": result.model_dump(mode="json"),
    }


def _competitor_profile_generation_output(result: Any, *, detail: str) -> dict[str, Any]:
    if detail == "full":
        return result.model_dump(mode="json")
    if detail != "summary":
        raise ValueError("unsupported competitor profile generation result detail")
    persisted = result.persisted
    profile = persisted.profile.profile_payload
    return {
        "status": result.status,
        "persisted": {
            "version": persisted.version.model_dump(mode="json"),
            "profile": {
                "target_sku_code": profile.target_sku_code,
                "analysis_state": profile.analysis_state,
                "conclusion_state": profile.conclusion_state,
                "profile_result_hash": profile.result_hash,
                "candidate_status_counts": profile.candidate_status_counts,
                "key_competitor_summary": [
                    row.model_dump(mode="json")
                    for row in profile.key_competitor_summary
                ],
                "source_lineage": profile.source_lineage,
            },
            "pair_count": len(persisted.pairs),
            "relation_count": len(persisted.relations),
            "selection_count": len(persisted.selections),
            "preview": persisted.preview,
        },
    }


def run_competitor_profile_build_request(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    context = Core3RepositoryContext(
        db=db,
        project_id=args.project_id,
        category_code=Core3CategoryCode(args.category_code),
    )
    request = build_production_generation_request(
        provider=CompetitorProfileInputProvider(context),
        profile_version=args.profile_version,
        generated_by=args.generated_by,
    )
    return {
        "status": AnalystStatus.OK.value,
        "command": args.command,
        "request": request.model_dump(mode="json"),
    }


def run_competitor_profile_read(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    consumption = _load_competitor_profile_consumption(db, args)
    return {
        "status": (
            AnalystStatus.OK.value
            if consumption.status == "available"
            else AnalystStatus.NOT_FOUND.value
        ),
        "command": args.command,
        "consumption": consumption.model_dump(mode="json"),
    }


def run_competitor_profile_preview(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    consumption = _load_competitor_profile_consumption(db, args)
    if consumption.status != "available":
        return {
            "status": AnalystStatus.NOT_FOUND.value,
            "command": args.command,
            "consumption": consumption.model_dump(mode="json"),
        }
    presentation = build_competitor_profile_presentation(
        consumption,
        with_report=args.with_report,
    )
    return {
        "status": AnalystStatus.OK.value,
        "command": args.command,
        "presentation": presentation.model_dump(mode="json"),
    }


def _load_competitor_profile_consumption(
    db: Session,
    args: argparse.Namespace,
):
    context = Core3RepositoryContext(
        db=db,
        project_id=args.project_id,
        category_code=Core3CategoryCode(args.category_code),
    )
    repository = CompetitorProfileRepository(context)
    return CompetitorProfileConsumptionService(
        CompetitorProfileReader(repository)
    ).load(
        CompetitorProfileReadRequest(
            project_id=args.project_id,
            category_code=args.category_code,
            release_scope_key=args.release_scope_key,
            target_sku_code=str(args.sku_code).strip().upper(),
            mode=args.mode,
            competitor_profile_version_id=args.competitor_profile_version_id,
            allow_draft_preview=bool(args.allow_draft_preview),
        )
    )


def _load_competitor_profile_generation_request(
    request_json: str,
) -> CompetitorProfileGenerationRequest:
    try:
        raw = (
            sys.stdin.read()
            if request_json == "-"
            else Path(request_json).read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise ValueError("竞品画像生成请求文件无法读取。") from exc
    return CompetitorProfileGenerationRequest.model_validate_json(raw)


def run_sellpoint_value_profile_generation(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    explicit = {
        "sku_code": getattr(args, "sku_code", None),
        "model_name": None,
        "query": None,
    }
    product_category = _infer_product_category(args.product_category, explicit)
    category_code = _infer_category_code(
        args.category_code,
        product_category,
        explicit,
    )
    service = CatForgeAnalystService(
        db,
        project_id=args.project_id,
        category_code=category_code,
    )
    context = service.build_context(
        batch_id=args.batch_id,
        product_category=product_category,
        market_window=args.market_window,
        analysis_population=args.analysis_population,
        resolve_latest=True,
    )
    provider = AnalystSellpointValueMaterializationInputProvider(
        repository=service.repository,
        atomic_handlers=service.atomic_handlers,
    )
    source_batch_ids = batch_ids_from_scope(context.batch_id)
    if not source_batch_ids:
        raise ValueError("用户卖点价值画像没有可用的来源批次。")
    persistence_batch_id = source_batch_ids[0]
    request = build_production_version_request(
        provider=provider,
        project_id=context.project_id,
        category_code=context.category_code,
        batch_id=persistence_batch_id,
        profile_version=args.profile_version,
        product_category=context.product_category,
        market_window=context.market_window,
        analysis_population=context.analysis_population,
        generated_by=args.generated_by,
        m12d_profile_version=getattr(args, "m12d_profile_version", None),
        source_batch_scope_id=context.batch_id,
    )
    lifecycle = SellpointValueProfileLifecycleService(
        repository=service.sellpoint_value_profile_repository,
        input_provider=provider,
    )
    if args.command == "sellpoint-value-profile-generate":
        readback = lifecycle.generate_draft(
            request,
            sku_code=str(args.sku_code).upper(),
        )
        return {
            "status": AnalystStatus.OK.value,
            "command": args.command,
            "project_id": context.project_id,
            "category_code": context.category_code,
            "batch_id": persistence_batch_id,
            "source_batch_scope_id": context.batch_id,
            "profile_version": request.profile_version,
            "version_result_hash": request.version_result_hash,
            "profile": readback.profile.model_dump(mode="json"),
            "persisted": readback.persisted.model_dump(mode="json"),
        }
    batch_result = lifecycle.batch_generate(
        request,
        resume_unfinished_only=not bool(args.regenerate_existing),
        page_size=args.page_size,
        max_new_skus=args.max_new_skus,
    )
    return {
        "status": AnalystStatus.OK.value,
        "command": args.command,
        "project_id": context.project_id,
        "category_code": context.category_code,
        "batch_id": persistence_batch_id,
        "source_batch_scope_id": context.batch_id,
        "profile_version": request.profile_version,
        "version_result_hash": request.version_result_hash,
        "batch_generation": batch_result.model_dump(mode="json"),
    }


def run_sellpoint_value_profile_v5_1_generation(
    db: Session,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Generate exactly one V5.1 draft from locked, already-saved inputs."""

    category_code = str(args.category_code).strip().upper()
    sku_code = str(args.sku_code).strip().upper()
    context = Core3RepositoryContext(
        db=db,
        project_id=str(args.project_id).strip(),
        category_code=Core3CategoryCode(category_code),
    )
    provider = SavedV5SellpointValueV51InputProvider(
        repository=SellpointValueProfileRepository(context),
        competitor_adapter=SellpointValueCompetitorProfileAdapter(
            CompetitorProfileAgentSnapshotRepository(context)
        ),
        source_profile_version=str(args.source_profile_version).strip(),
    )
    request = provider.build_version_request(
        project_id=context.project_id,
        category_code=category_code,
        batch_id=str(args.batch_id).strip(),
        profile_version=str(args.profile_version).strip(),
        expected_sku_codes=[sku_code],
        generated_by=str(args.generated_by).strip(),
    )
    readback = SellpointValueV51GenerationService(
        repository=SellpointValueV51Repository(context),
        input_provider=provider,
    ).generate_draft(
        request,
        sku_code=sku_code,
    )
    payload = (
        readback.model_dump(mode="json")
        if args.result_detail == "full"
        else _sellpoint_value_v5_1_generation_summary(readback)
    )
    return {
        "status": AnalystStatus.OK.value,
        "command": args.command,
        "generation": payload,
    }


def _sellpoint_value_v5_1_generation_summary(readback: Any) -> dict[str, Any]:
    profile = readback.profile
    version = readback.persisted.version
    investments = [
        decision
        for value in profile.values
        for decision in value.investment_decisions
    ]
    return {
        "sellpoint_value_profile_version_id": (
            version.sellpoint_value_profile_version_id
        ),
        "profile_version": version.profile_version,
        "release_status": str(version.release_status),
        "is_current": version.is_current,
        "processing_status": version.processing_status,
        "release_quality_status": str(version.release_quality_status),
        "target_sku_code": profile.target.sku_code,
        "result_hash": profile.result_hash,
        "input_fingerprint": profile.input_fingerprint,
        "version_result_hash": version.result_hash,
        "candidate_universe_fingerprint": (
            version.candidate_universe_fingerprint
        ),
        "competitor_profile_version_id": (
            profile.competitor_source.competitor_profile_version_id
        ),
        "competitor_source_result_hash": (
            profile.competitor_source.source_result_hash
        ),
        "competitor_source_version_result_hash": (
            profile.competitor_source.source_version_result_hash
        ),
        "formal_competitor_count": len(
            profile.candidate_pools.formal_competitors
        ),
        "priority_order": list(profile.candidate_pools.priority_order),
        "analysis_reference_count": len(
            profile.candidate_pools.analysis_references
        ),
        "question_candidate_set_count": len(
            profile.candidate_pools.question_candidate_sets
        ),
        "value_count": len(profile.values),
        "value_conclusions": [
            {
                "value_bundle_code": value.value_bundle_code,
                "value_bundle_name_cn": value.value_bundle_name_cn,
                "status": str(value.value_conclusion.status),
                "capability_codes": list(value.capability_codes),
                "direct_market_result_count": len(
                    value.direct_market_results
                ),
                "parameter_group_result_count": len(
                    value.parameter_group_results
                ),
                "market_archetype_result_count": len(
                    value.market_archetype_results
                ),
                "strict_wtp_status": (
                    str(value.strict_market_implied_wtp.status)
                    if value.strict_market_implied_wtp is not None
                    else None
                ),
            }
            for value in profile.values
        ],
        "investment_counts": {
            classification: sum(
                decision.classification == classification
                for decision in investments
            )
            for classification in sorted(
                {str(decision.classification) for decision in investments}
            )
        },
        "sku_conclusion_status": str(profile.sku_conclusion.status),
        "consumer_status": profile.sku_conclusion.consumer_status,
        "source_lineage": [
            row.model_dump(mode="json") for row in profile.source_lineage
        ],
    }


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


def sku_purchase_reason(
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
    taxonomy_version: str | None = None,
    max_anchors: int = 8,
) -> dict[str, Any]:
    normalized_product_category = _infer_product_category(
        product_category,
        {"query": query, "sku_code": sku_code, "model_name": model_name},
    )
    normalized_category_code = _infer_category_code(
        category_code,
        normalized_product_category,
        {"query": query, "sku_code": sku_code, "model_name": model_name},
    )
    service = CatForgeAnalystService(
        db,
        project_id=project_id,
        category_code=normalized_category_code,
    )
    context = service.build_context(
        batch_id=batch_id,
        product_category=normalized_product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        resolve_latest=True,
    )
    resolved_sku_code = _resolve_sku_code_for_purchase_reason(
        db,
        context=context,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
    )
    preview = build_sku_purchase_reason_preview(
        db,
        project_id=project_id,
        category_code=context.category_code,
        batch_id=context.batch_id,
        product_category=context.product_category,
        sku_code=resolved_sku_code,
        taxonomy_version=taxonomy_version or _default_purchase_reason_taxonomy_version(normalized_product_category),
        max_anchors=max_anchors,
    )
    result = base_result(
        status=AnalystStatus.OK,
        command="sku-purchase-reason",
        context=AnalystContext(
            project_id=project_id,
            category_code=context.category_code,
            batch_id=context.batch_id,
            product_category=context.product_category,
            market_window=context.market_window,
            analysis_population=context.analysis_population,
        ),
        target=preview["sku"],
        result={"sku_purchase_reason": preview},
        evidence=_purchase_reason_preview_evidence(preview),
        limitations=preview.get("limitations") or [],
        answer_outline=[
            f"已生成 {preview['sku'].get('display_name_cn') or resolved_sku_code} 的成交理由画像预览。",
        ],
    )
    result["markdown_preview"] = preview["markdown_preview"]
    return result


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


def sellpoint_value_pm(
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
    max_chat_chars: int = 600,
    report_title: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="sellpoint-value-pm",
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
    profile_access_mode: str = "formal",
    competitor_profile_version_id: str | None = None,
    competitor_profile_release_scope_key: str | None = None,
    allow_draft_preview: bool = False,
    legacy_live_analysis: bool = False,
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
        profile_access_mode=profile_access_mode,
        competitor_profile_version_id=competitor_profile_version_id,
        competitor_profile_release_scope_key=(
            competitor_profile_release_scope_key
        ),
        allow_draft_preview=allow_draft_preview,
        legacy_live_analysis=legacy_live_analysis,
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


def low_sales_diagnosis(
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
    max_chat_chars: int = 800,
    report_title: str | None = None,
) -> dict[str, Any]:
    return run_analyst_command(
        db,
        command="low-sales-diagnosis",
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
    profile_access_mode: str = "formal",
    competitor_profile_version_id: str | None = None,
    competitor_profile_release_scope_key: str | None = None,
    allow_draft_preview: bool = False,
    legacy_live_analysis: bool = False,
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
        profile_access_mode=profile_access_mode,
        competitor_profile_version_id=competitor_profile_version_id,
        competitor_profile_release_scope_key=(
            competitor_profile_release_scope_key
        ),
        allow_draft_preview=allow_draft_preview,
        legacy_live_analysis=legacy_live_analysis,
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
    profile_competitor_read = (
        command == "competitor-set"
        and not bool(kwargs.get("legacy_live_analysis"))
        and bool(str(kwargs.get("sku_code") or "").strip())
    )
    if command == "ask" and not bool(kwargs.get("legacy_live_analysis")):
        route = route_question(
            str(kwargs.get("question") or ""),
            explicit_params=kwargs,
        )
        routed_sku_code = (
            kwargs.get("sku_code") or route.extracted_params.get("sku_code")
        )
        profile_competitor_read = (
            route.command == "competitor-set"
            and bool(str(routed_sku_code or "").strip())
        )
    context = service.build_context(
        batch_id=batch_id,
        product_category=product_category,
        market_window=market_window,
        analysis_population=analysis_population,
        resolve_latest=(
            command != "list-abilities" and not profile_competitor_read
        ),
    )
    if command == "list-abilities":
        return service.list_abilities(context, ability_type=kwargs.get("ability_type"))
    return service.dispatch(command, context, **_clean_kwargs(kwargs))


def _resolve_sku_code_for_purchase_reason(
    db: Session,
    *,
    context: AnalystContext,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
) -> str:
    if sku_code and sku_code.strip():
        return sku_code.strip()
    if not (query and query.strip()) and not (model_name and model_name.strip()):
        raise CatForgeAnalystError("请提供 --sku-code、--model-name 或 --query。")
    resolved = resolve_sku(
        db,
        project_id=context.project_id,
        category_code=context.category_code,
        batch_id=context.batch_id,
        product_category=context.product_category,
        query=query,
        model_name=model_name,
        limit=DEFAULT_CANDIDATE_LIMIT,
    )
    if resolved.get("status") != AnalystStatus.OK.value:
        raise CatForgeAnalystError(str(resolved.get("message_cn") or "无法解析 SKU。"))
    resolved_sku = ((resolved.get("result") or {}).get("resolved_sku") or resolved.get("target") or {}).get("sku_code")
    if not resolved_sku:
        raise CatForgeAnalystError("无法解析 SKU，请提供明确的 SKU code。")
    return str(resolved_sku)


def _purchase_reason_preview_evidence(preview: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in preview.get("input_status") or []:
        evidence.append(
            {
                "source_module": item.get("source"),
                "source_name_cn": item.get("source_cn"),
                "status": item.get("status"),
                "record_count": item.get("record_count"),
            }
        )
    return evidence


def _infer_product_category(product_category: str, kwargs: dict[str, Any]) -> str:
    normalized = (product_category or DEFAULT_PRODUCT_CATEGORY).strip().lower()
    if normalized in {"ac", "空调"}:
        return "ac"
    if normalized in {"tv", "电视", "彩电"} and _context_mentions_ac(kwargs):
        return "ac"
    return normalized


def _default_purchase_reason_taxonomy_version(product_category: str) -> str:
    if (product_category or "").strip().upper() == "AC":
        return CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION
    return CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION


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
    chat_id = getattr(args, "feishu_chat_id", None)
    reply_message_id = getattr(args, "feishu_reply_message_id", None)
    if not chat_id and not reply_message_id:
        return
    payload = result.get("result") or {}
    competitor_answer = payload.get("competitor_answer") or {}
    claim_value_answer = payload.get("claim_value_answer") or {}
    sellpoint_value_pm_answer = payload.get("sellpoint_value_pm_answer") or {}
    sellpoint_value_pm_v5_answer = payload.get("sellpoint_value_pm_v5_answer") or {}
    sellpoint_value_pm_v4_answer = payload.get("sellpoint_value_pm_v4_answer") or {}
    answer_key = ""
    card = None
    if competitor_answer.get("feishu_card_payload"):
        answer_key = "competitor_answer"
        card = competitor_answer.get("feishu_card_payload")
    elif claim_value_answer.get("feishu_card_payload"):
        answer_key = "claim_value_answer"
        card = claim_value_answer.get("feishu_card_payload")
    elif sellpoint_value_pm_answer.get("feishu_card_payload"):
        answer_key = "sellpoint_value_pm_answer"
        card = sellpoint_value_pm_answer.get("feishu_card_payload")
    elif sellpoint_value_pm_v5_answer.get("feishu_card_payload"):
        answer_key = "sellpoint_value_pm_v5_answer"
        card = sellpoint_value_pm_v5_answer.get("feishu_card_payload")
    elif sellpoint_value_pm_v4_answer.get("feishu_card_payload"):
        answer_key = "sellpoint_value_pm_v4_answer"
        card = sellpoint_value_pm_v4_answer.get("feishu_card_payload")
    else:
        return
    if chat_id:
        delivery = competitor_answer_renderer.publish_feishu_card_message(
            card=card,
            chat_id=chat_id,
            idempotency_key=getattr(args, "feishu_card_idempotency_key", None),
        )
        if delivery.status != "sent" and reply_message_id:
            delivery = competitor_answer_renderer.publish_feishu_card_reply(
                card=card,
                reply_message_id=reply_message_id,
                reply_in_thread=bool(getattr(args, "feishu_reply_in_thread", False)),
                idempotency_key=getattr(args, "feishu_card_idempotency_key", None),
            )
    else:
        delivery = competitor_answer_renderer.publish_feishu_card_reply(
            card=card,
            reply_message_id=reply_message_id,
            reply_in_thread=bool(getattr(args, "feishu_reply_in_thread", False)),
            idempotency_key=getattr(args, "feishu_card_idempotency_key", None),
        )
    delivery_payload = delivery.to_dict()
    if answer_key == "claim_value_answer" and delivery_payload.get("status") == "sent":
        delivery_payload["message_cn"] = "已发送飞书用户卖点价值看板卡片。"
    if answer_key == "sellpoint_value_pm_answer" and delivery_payload.get("status") == "sent":
        delivery_payload["message_cn"] = "已发送飞书卖点经营盘卡片。"
    if answer_key == "sellpoint_value_pm_v4_answer" and delivery_payload.get("status") == "sent":
        delivery_payload["message_cn"] = "已发送飞书用户价值结构与市场兑现卡片。"
    if answer_key == "sellpoint_value_pm_v5_answer" and delivery_payload.get("status") == "sent":
        delivery_payload["message_cn"] = "已发送飞书用户感知价值与市场兑现卡片。"
    if not isinstance(result.get("result"), dict):
        result["result"] = {}
    if not isinstance(result["result"].get(answer_key), dict):
        result["result"][answer_key] = {}
    result["result"][answer_key]["feishu_card_delivery"] = delivery_payload


def emit_result(result: dict[str, Any], output_format: str, *, feishu_card_only: bool = False) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, default=json_default, indent=2, sort_keys=True))
        return
    if output_format == "markdown":
        markdown = result.get("markdown_preview") or ((result.get("result") or {}).get("sku_purchase_reason") or {}).get(
            "markdown_preview"
        )
        if markdown:
            print(markdown)
            return
    card_delivery = _feishu_card_delivery(result)
    if card_delivery:
        delivery_text = format_feishu_card_delivery_text(result)
        if delivery_text:
            print(delivery_text)
            return
    if feishu_card_only:
        print("未发送飞书看板卡片：缺少发送结果。")
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
    payload = result.get("result") or {}
    competitor_answer = payload.get("competitor_answer") or {}
    claim_value_answer = payload.get("claim_value_answer") or {}
    sellpoint_value_pm_answer = payload.get("sellpoint_value_pm_answer") or {}
    sellpoint_value_pm_v5_answer = payload.get("sellpoint_value_pm_v5_answer") or {}
    sellpoint_value_pm_v4_answer = payload.get("sellpoint_value_pm_v4_answer") or {}
    delivery = (
        competitor_answer.get("feishu_card_delivery")
        or claim_value_answer.get("feishu_card_delivery")
        or sellpoint_value_pm_answer.get("feishu_card_delivery")
        or sellpoint_value_pm_v5_answer.get("feishu_card_delivery")
        or sellpoint_value_pm_v4_answer.get("feishu_card_delivery")
    )
    return delivery if isinstance(delivery, dict) else {}


def format_feishu_card_delivery_text(result: dict[str, Any]) -> str:
    payload = result.get("result") or {}
    competitor_answer = payload.get("competitor_answer") or {}
    claim_value_answer = payload.get("claim_value_answer") or {}
    sellpoint_value_pm_answer = payload.get("sellpoint_value_pm_answer") or {}
    sellpoint_value_pm_v5_answer = payload.get("sellpoint_value_pm_v5_answer") or {}
    sellpoint_value_pm_v4_answer = payload.get("sellpoint_value_pm_v4_answer") or {}
    delivery = _feishu_card_delivery(result)
    if delivery.get("status") == "sent":
        return str(delivery.get("message_cn") or "已发送飞书竞品看板卡片。")
    if delivery.get("message_cn"):
        return str(delivery["message_cn"])
    if delivery.get("status") == "failed":
        return "飞书卡片发送失败。"
    if delivery.get("status"):
        return "未发送飞书看板卡片。"
    return str(
        competitor_answer.get("short_answer")
        or claim_value_answer.get("short_answer")
        or sellpoint_value_pm_answer.get("short_answer")
        or sellpoint_value_pm_v5_answer.get("short_answer")
        or sellpoint_value_pm_v4_answer.get("short_answer")
        or ""
    )


def format_business_text(result: dict[str, Any]) -> str:
    payload = result.get("result") or {}
    if result.get("status") == "ambiguous" and payload.get("candidates"):
        return _format_ambiguous_sku_text(result)
    profile_answer = payload.get("sellpoint_value_profile_answer") or {}
    if profile_answer.get("direct_answer_cn"):
        facts = profile_answer.get("profile_facts") or []
        sections = [
            str(profile_answer["direct_answer_cn"]),
            *(
                f"画像事实｜{row.get('summary_cn')}"
                for row in facts
                if row.get("summary_cn")
            ),
            f"产品工作含义｜{profile_answer.get('work_implication_cn')}",
            f"证据边界｜{profile_answer.get('evidence_boundary_cn')}",
            (
                f"画像版本｜{profile_answer.get('profile_version')}｜"
                f"结果编号 {profile_answer.get('result_hash')}"
            ),
        ]
        return "\n".join(item for item in sections if item and not item.endswith("｜None"))
    competitor_answer = payload.get("competitor_answer") or {}
    if competitor_answer.get("short_answer"):
        return str(competitor_answer["short_answer"])
    claim_value_answer = payload.get("claim_value_answer") or {}
    if claim_value_answer.get("short_answer"):
        return str(claim_value_answer["short_answer"])
    sellpoint_value_pm_answer = payload.get("sellpoint_value_pm_answer") or {}
    if sellpoint_value_pm_answer.get("short_answer"):
        return str(sellpoint_value_pm_answer["short_answer"])
    sellpoint_value_pm_v5_answer = payload.get("sellpoint_value_pm_v5_answer") or {}
    if sellpoint_value_pm_v5_answer.get("short_answer"):
        return str(sellpoint_value_pm_v5_answer["short_answer"])
    sellpoint_value_pm_v4_answer = payload.get("sellpoint_value_pm_v4_answer") or {}
    if sellpoint_value_pm_v4_answer.get("short_answer"):
        return str(sellpoint_value_pm_v4_answer["short_answer"])
    if "sellpoint_value_pm_v4" in payload:
        report = payload.get("sellpoint_value_pm_v4") or {}
        return str(report.get("headline_cn") or "已生成产品经理用户价值账。")
    if "sellpoint_value_pm_v5" in payload:
        return "已生成产品经理用户感知价值与市场兑现报告。"
    if "sellpoint_value_pm" in payload:
        analysis = payload.get("sellpoint_value_pm") or {}
        return str(analysis.get("headline_cn") or "已生成产品经理版卖点称重结果。")
    if "competitor_set" in payload:
        return _format_competitor_set_text(result)
    if "why_sales_diff" in payload:
        return _format_why_sales_diff_text(result)
    low_sales_answer = payload.get("low_sales_answer") or {}
    if low_sales_answer.get("short_answer"):
        return str(low_sales_answer["short_answer"])
    if "low_sales_diagnosis" in payload:
        return _format_low_sales_diagnosis_text(result)
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


def _format_low_sales_diagnosis_text(result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    payload = ((result.get("result") or {}).get("low_sales_diagnosis") or {})
    target_name = _brand_model(target)
    sales_status = payload.get("sales_status") or {}
    status = str(sales_status.get("status") or "uncertain")
    basis = str(sales_status.get("basis_cn") or "").strip()
    status_line = {
        "weak": f"{target_name} 在当前可比线上样本中属于相对偏弱。",
        "not_weak": f"{target_name} 在当前可比线上样本中不属于明显低销量 SKU。",
        "mixed": f"{target_name} 的销量表现是混合状态，对部分竞品偏弱、对部分竞品不弱。",
        "uncertain": f"当前样本不足以判断 {target_name} 是否真的卖得弱。",
    }.get(status, f"当前样本不足以判断 {target_name} 是否真的卖得弱。")
    if basis:
        status_line = f"{status_line}{basis}"

    reasons = [row for row in payload.get("reason_ranking") or [] if isinstance(row, dict)]
    reason_chunks = []
    for row in reasons[:3]:
        name = str(row.get("reason_name_cn") or "").strip()
        root_cause = str(row.get("root_cause_cn") or row.get("summary_cn") or "").strip("。")
        observation = _low_sales_cli_observation(row).strip("。")
        decision = str(row.get("decision_implication_cn") or "").strip("。")
        parts = []
        if root_cause:
            parts.append(root_cause)
        if observation:
            parts.append(f"证据：{observation}")
        if decision:
            parts.append(f"决策含义：{decision}")
        if name and parts:
            reason_chunks.append(f"{name}：{'；'.join(parts)}")
        elif parts:
            reason_chunks.append("；".join(parts))

    actions = payload.get("action_plan") or {}
    action_chunks = []
    for key in ("short_term_actions", "mid_term_actions"):
        for row in [item for item in actions.get(key) or [] if isinstance(item, dict)][:2]:
            summary = str(row.get("summary_cn") or "").strip("。")
            if summary:
                action_chunks.append(summary)
        if action_chunks:
            break

    lines = [status_line]
    if reason_chunks:
        lines.append(f"主要诊断优先看：{'；'.join(reason_chunks)}。")
    if action_chunks:
        lines.append(f"建议先做：{'；'.join(action_chunks)}。")
    lines.append("当前不能判断广告、库存、促销和毛利原因，因为缺少对应数据。")
    limitations = [_sanitize_business_limitation(item) for item in result.get("limitations") or [] if item]
    limitations = [item for item in limitations if item]
    if limitations:
        lines.append(f"补充限制：{'；'.join(str(item) for item in limitations[:3])}。")
    return "\n".join(lines)


def _low_sales_cli_observation(row: dict[str, Any]) -> str:
    points = [str(item).strip() for item in row.get("observation_points") or row.get("detail_points") or [] if str(item).strip()]
    return points[0] if points else ""


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
            if category == "人无我有型支付价值卖点":
                note = _claim_value_cli_unique_note(group)
                lines.append(
                    f"- {group['claim_name']}：本品在同战场具备稀缺卖点或关键参数优势，可能提高用户最高支付意愿；"
                    f"当前对照不足，暂不量化金额；"
                    f"覆盖价值战场：{'、'.join(group['battlefields'][:4]) if group['battlefields'] else '相关战场待补充'}。"
                    f"{note}"
                )
                continue
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
    target_rows = [row for row in rows if _claim_value_cli_target_has_claim(row)]
    gap_rows = [row for row in rows if not _claim_value_cli_target_has_claim(row)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in target_rows:
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
    competitor_gaps = [row for row in gap_rows if str(row.get("business_claim_type_cn") or "") == "竞品拦截卖点"]
    if competitor_gaps:
        lines.append("竞品拦截/机会缺口（非本品当前已成立卖点）：")
        for item in competitor_gaps[:5]:
            claim_name = str(item.get("claim_name") or item.get("claim_code") or "未命名方向")
            contexts = "、".join(str(value) for value in (item.get("main_contexts") or [])[:4]) or "相关价值战场"
            lines.append(f"- {claim_name}：{contexts}。")
    lines.append("说明：以上为 SKU 层汇总结果，计算时先在单个价值战场内判断卖点支付价值，再按战场相关度汇总；用户任务、目标客群和整体市场池作为解释证据，不直接重复累加。")
    return "\n".join(lines)


def _claim_value_cli_unique_note(group: dict[str, Any]) -> str:
    for row in group.get("battlefield_rows") or []:
        supporting = row.get("supporting_dimensions") or {}
        scorecard = supporting.get("unique_payment_potential_scorecard") if isinstance(supporting, dict) else None
        if not isinstance(scorecard, dict):
            scorecard = ((row.get("scorecard") or {}).get("unique_payment_potential") or {}) if isinstance(row.get("scorecard"), dict) else {}
        if not isinstance(scorecard, dict) or not scorecard:
            continue
        level = str(scorecard.get("potential_level_cn") or "").strip()
        reason = str(scorecard.get("no_amount_reason_cn") or "").strip()
        condition = str(scorecard.get("verification_condition_cn") or "").strip()
        parts = []
        if level:
            parts.append(f"潜力判断：{level}")
        if reason:
            parts.append(f"不量化原因：{reason}")
        if condition:
            parts.append(f"验证条件：{condition}")
        if parts:
            return "".join(f"{part}。" for part in parts)
    return ""


def _claim_value_cli_target_has_claim(row: dict[str, Any]) -> bool:
    if "target_has_claim" in row:
        return bool(row.get("target_has_claim"))
    if str(row.get("claim_source_type") or "") == "competitor_opportunity_gap":
        return False
    if str(row.get("business_claim_type_cn") or "") == "竞品拦截卖点":
        return False
    evidence = row.get("evidence_strength") or {}
    claim_strength = _decimal(evidence.get("claim")) or Decimal("0")
    if claim_strength > 0:
        return True
    return True


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
    if category == "人无我有型支付价值卖点":
        return "本品在同战场具备稀缺卖点或关键参数优势，可能提高用户最高支付意愿；当前对照不足，暂不量化金额"
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
        "人无我有型支付价值卖点",
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
        "人无我有型支付价值卖点",
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
        "unique_payment_potential": "人无我有型支付价值卖点",
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
