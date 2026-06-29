"""Publish CatForge analysis results to business workbenches."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any

from app.core.database import SessionLocal
from app.services.core3_real_data.publish.base_client import BaseClientError, LarkCliBaseClient
from app.services.core3_real_data.publish.base_publisher import BaseWorkbenchPublisher
from app.services.core3_real_data.publish.base_schema import SYNC_SCOPES
from app.services.core3_real_data.publish.sync_state import load_base_workbench_config


DEFAULT_PROJECT_ID = os.getenv("CATFORGE_PROJECT_ID", "core3_mvp")
DEFAULT_CATEGORY_CODE = os.getenv("CATFORGE_CATEGORY_CODE", "TV")
DEFAULT_PRODUCT_CATEGORY = os.getenv("CATFORGE_PRODUCT_CATEGORY", "tv")
DEFAULT_MARKET_WINDOW = "full_observed_window"
DEFAULT_ANALYSIS_POPULATION = "fact_complete_with_comment"
DEFAULT_CLAIM_ANALYSIS_POPULATION = "claim_value_ready_with_comment"
DEFAULT_BASE_NAME = "小奥家电市场分析工作台"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (RuntimeError, BaseClientError) as exc:
        payload = {"status": "blocked", "message_cn": str(exc)}
        emit(payload, args.format)
        return 2
    emit(result.to_dict() if hasattr(result, "to_dict") else result, args.format)
    return 0 if getattr(result, "status", "ok") not in {"failed", "blocked"} else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.catforge_publish",
        description="Publish CatForge analysis result summaries to Feishu Base workbench.",
    )
    subparsers = parser.add_subparsers(dest="resource", required=True)
    base = subparsers.add_parser("base", help="Manage the XiaoAo Feishu Base workbench.")
    base_subparsers = base.add_subparsers(dest="action", required=True)

    init_parser = base_subparsers.add_parser("init", help="Create or verify the Feishu Base workbench schema.")
    add_context_args(init_parser)
    init_parser.add_argument("--base-name", default=DEFAULT_BASE_NAME)
    add_format_arg(init_parser)

    sync_parser = base_subparsers.add_parser("sync", help="Sync one publish scope.")
    add_context_args(sync_parser)
    sync_parser.add_argument("--scope", choices=SYNC_SCOPES, required=True)
    sync_parser.add_argument("--batch-id", default="latest")
    sync_parser.add_argument("--dry-run", action="store_true")
    sync_parser.add_argument("--limit", type=int)
    sync_parser.add_argument("--allow-schema-update", action="store_true")
    add_format_arg(sync_parser)

    sync_all_parser = base_subparsers.add_parser("sync-all", help="Sync all phase-1 publish scopes.")
    add_context_args(sync_all_parser)
    sync_all_parser.add_argument("--batch-id", default="latest")
    sync_all_parser.add_argument("--dry-run", action="store_true")
    sync_all_parser.add_argument("--limit", type=int)
    sync_all_parser.add_argument("--allow-schema-update", action="store_true")
    add_format_arg(sync_all_parser)

    status_parser = base_subparsers.add_parser("status", help="Inspect workbench configuration status.")
    add_context_args(status_parser)
    add_format_arg(status_parser)

    open_parser = base_subparsers.add_parser("open", help="Return the configured workbench URL.")
    add_context_args(open_parser)
    add_format_arg(open_parser)
    return parser


def add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE)
    parser.add_argument("--category", choices=("tv", "ac"), default=DEFAULT_PRODUCT_CATEGORY)
    parser.add_argument("--market-window", default=DEFAULT_MARKET_WINDOW)
    parser.add_argument("--analysis-population", default=DEFAULT_ANALYSIS_POPULATION)
    parser.add_argument("--claim-analysis-population", default=DEFAULT_CLAIM_ANALYSIS_POPULATION)


def add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="json")


def run(args: argparse.Namespace) -> Any:
    config = load_base_workbench_config()
    client = LarkCliBaseClient(cli_bin=config.cli_bin)
    with SessionLocal() as db:
        publisher = BaseWorkbenchPublisher(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            product_category=args.category,
            market_window=args.market_window,
            analysis_population=args.analysis_population,
            claim_analysis_population=args.claim_analysis_population,
            config=config,
            client=client,
        )
        if args.action == "init":
            return publisher.init_base(base_name=args.base_name)
        if args.action == "sync":
            result = publisher.sync_scope(
                scope=args.scope,
                batch_id=args.batch_id,
                dry_run=args.dry_run,
                limit=args.limit,
                allow_schema_update=args.allow_schema_update,
            )
            resolved_batch = publisher.extractor.resolve_batch_id(args.batch_id)
            return {
                "status": result.status,
                "category_code": args.category_code.upper(),
                "batch_id": resolved_batch,
                "base_url": publisher.base_url,
                "message_cn": result.message_cn,
                "scopes": [asdict(result)],
            }
        if args.action == "sync-all":
            return publisher.sync_all(
                batch_id=args.batch_id,
                dry_run=args.dry_run,
                limit=args.limit,
                allow_schema_update=args.allow_schema_update,
            )
        if args.action == "status":
            return publisher.status()
        if args.action == "open":
            return publisher.open()
    raise RuntimeError(f"unknown action: {args.action}")


def emit(payload: Any, output_format: str) -> None:
    data = _jsonable(payload)
    if output_format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(render_text(data))


def render_text(data: dict[str, Any]) -> str:
    status = data.get("status")
    if status in {"blocked", "failed"}:
        return str(data.get("message_cn") or "发布失败。")
    lines = [str(data.get("message_cn") or "发布命令已完成。")]
    if data.get("category_code"):
        lines.append(f"品类：{data['category_code']}")
    if data.get("batch_id"):
        lines.append(f"批次：{data['batch_id']}")
    if data.get("base_url"):
        lines.append(f"工作台：{data['base_url']}")
    scopes = data.get("scopes") or []
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        label = scope.get("table_name") or scope.get("scope")
        parts = [f"{label}：{scope.get('status')}"]
        if scope.get("extracted_count") is not None:
            parts.append(f"提取 {scope.get('extracted_count')} 行")
        if scope.get("created_count"):
            parts.append(f"新增 {scope.get('created_count')} 行")
        if scope.get("updated_count"):
            parts.append(f"更新 {scope.get('updated_count')} 行")
        if scope.get("message_cn"):
            parts.append(str(scope["message_cn"]))
        lines.append("；".join(parts))
    return "\n".join(lines)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    return value


if __name__ == "__main__":
    sys.exit(main())
