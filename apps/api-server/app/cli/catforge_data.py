"""Business-level CatForge data operations for local and server-side agents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import entities
from app.schemas.core3_real_data import Core3SourceBatchRegisterRequest
from app.services.core3_real_data.cleaning_repositories import CleaningQueryRepository
from app.services.core3_real_data.cleaning_runner import CleaningQualityRunner
from app.services.core3_real_data.constants import Core3SourceBatchStatus, Core3SourceBatchType
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.source_registry_service import SourceRegistryRunner


DEFAULT_PROJECT_ID = os.getenv("CATFORGE_PROJECT_ID", "core3_mvp")
DEFAULT_CATEGORY_CODE = os.getenv("CATFORGE_CATEGORY_CODE", "TV")
CONSUMABLE_BATCH_STATUSES = (
    Core3SourceBatchStatus.REGISTERED.value,
    Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value,
)


class CliError(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-new-data":
            payload = _prepare_new_data(args)
        elif args.command == "inspect-data-quality":
            payload = _inspect_data_quality(args)
        else:
            parser.error("missing command")
    except CliError as exc:
        _print_payload(
            {
                "status": "blocked",
                "message_cn": str(exc),
            },
            output_format=getattr(args, "format", "json"),
        )
        return 2

    _print_payload(payload, output_format=args.format)
    return 0 if payload.get("status") not in {"failed", "blocked"} else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catforge-data",
        description="CatForge data preparation and quality inspection commands.",
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare-new-data",
        help="Register optional raw changes and run preliminary cleaning only.",
    )
    _add_common_project_args(prepare)
    prepare.add_argument("--batch-id", default="latest")
    prepare.add_argument(
        "--register-source-batch",
        choices=("none", "incremental", "full"),
        default="incremental",
        help=(
            "Create a source batch before cleaning. Defaults to incremental so new-data "
            "preprocessing runs source registration and preliminary cleaning together. "
            "Use none with --batch-id to clean an existing batch."
        ),
    )
    prepare.add_argument(
        "--source-tables",
        default="week_sales_data,attribute_data,selling_points_data,comment_data",
        help="Comma-separated raw tables for source registration.",
    )
    prepare.add_argument("--sku-code", action="append", default=[], help="Restrict cleaning to one SKU. Repeatable.")
    prepare.add_argument("--sku-batch-size", type=int, default=50, help="SKU chunk size for M01 cleaning.")
    prepare.add_argument("--limit-skus", type=int, default=None, help="Limit target SKUs for smoke tests.")
    prepare.add_argument("--include-no-change", action="store_true")
    prepare.add_argument(
        "--allow-full-scan",
        action="store_true",
        help="Run M01 without SKU chunking if no target SKU list exists.",
    )
    prepare.add_argument("--dry-run", action="store_true")
    prepare.add_argument("--run-id", default=None)
    prepare.add_argument("--module-run-id", default=None)

    inspect_parser = subparsers.add_parser(
        "inspect-data-quality",
        help="Inspect M01 preliminary cleaning and quality coverage.",
    )
    _add_common_project_args(inspect_parser)
    inspect_parser.add_argument("--batch-id", default="latest")
    inspect_parser.add_argument("--limit-skus", type=int, default=20)
    return parser


def _add_common_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE)
    parser.add_argument("--format", choices=("json", "text"), default="json")


def _prepare_new_data(args: argparse.Namespace) -> dict[str, Any]:
    with SessionLocal() as db:
        batch_id = args.batch_id
        source_registration: dict[str, Any] | None = None
        if args.dry_run and args.register_source_batch != "none":
            return {
                "command": "prepare-new-data",
                "status": "dry_run",
                "source_registration": {
                    "will_register_source_batch": True,
                    "batch_type": args.register_source_batch,
                    "source_tables": _parse_csv(args.source_tables),
                },
                "plan": {
                    "batch_id": None,
                    "sku_count": None,
                    "chunk_count": None,
                    "sku_batch_size": args.sku_batch_size,
                    "source_registration_mode": args.register_source_batch,
                    "include_no_change": bool(args.include_no_change),
                    "will_run_modules": ["M00", "M01"],
                    "will_not_run_modules": ["M02", "M05"],
                },
                "message_cn": "这是数据预处理执行计划，尚未登记源批次，也未写入清洗结果。",
            }

        if args.register_source_batch != "none":
            source_registration = _register_source_batch(db, args)
            batch_id = str(source_registration["batch_id"])
        else:
            batch_id = _resolve_batch_id(
                db,
                project_id=args.project_id,
                category_code=args.category_code,
                batch_id=batch_id,
            )

        target_skus = _resolve_target_skus(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=batch_id,
            requested_skus=args.sku_code,
            limit=args.limit_skus,
        )
        if not target_skus and not args.allow_full_scan:
            raise CliError(
                f"未找到 batch {batch_id} 的目标 SKU；如确认要全量扫描，请加 --allow-full-scan。"
            )

        chunks = _sku_chunks(target_skus, args.sku_batch_size) if target_skus else [()]
        plan = {
            "batch_id": batch_id,
            "sku_count": len(target_skus),
            "chunk_count": len(chunks),
            "sku_batch_size": args.sku_batch_size,
            "source_registration_mode": args.register_source_batch,
            "include_no_change": bool(args.include_no_change),
            "will_run_modules": ["M00", "M01"] if args.register_source_batch != "none" else ["M01"],
            "will_not_run_modules": ["M02", "M05"],
        }
        if args.dry_run:
            return {
                "command": "prepare-new-data",
                "status": "dry_run",
                "source_registration": source_registration,
                "plan": plan,
                "message_cn": "这是数据预处理执行计划，尚未写入清洗结果。",
            }

        execution_label = args.run_id or _new_cli_run_id("m01")
        run_id = args.run_id
        chunk_results: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        runner = CleaningQualityRunner(db)
        for index, chunk in enumerate(chunks, start=1):
            result = runner.run_batch(
                project_id=args.project_id,
                category_code=args.category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=args.module_run_id,
                include_no_change=bool(args.include_no_change),
                target_sku_codes=tuple(chunk),
            )
            db.commit()
            last_result = _module_result_payload(result)
            chunk_results.append(
                {
                    "chunk_index": index,
                    "sku_count": len(chunk),
                    "status": last_result["status"],
                    "input_count": last_result["input_count"],
                    "output_count": last_result["output_count"],
                }
            )
            if last_result["status"] in {"failed", "blocked"}:
                break

        status = "success"
        if last_result and last_result["status"] in {"failed", "blocked"}:
            status = last_result["status"]
        elif last_result and last_result["status"] == "warning":
            status = "warning"

        message_cn = (
            "已完成数据预处理：已执行源数据登记和初步清洗过滤，未进入证据或评论语义分析阶段。"
            if args.register_source_batch != "none"
            else "已完成已有批次初步清洗过滤，未进入证据或评论语义分析阶段。"
        )

        return {
            "command": "prepare-new-data",
            "status": status,
            "batch_id": batch_id,
            "execution_label": execution_label,
            "source_registration": source_registration,
            "plan": plan,
            "processed_chunks": chunk_results,
            "m01_summary": last_result["summary_json"] if last_result else {},
            "message_cn": message_cn,
        }


def _inspect_data_quality(args: argparse.Namespace) -> dict[str, Any]:
    with SessionLocal() as db:
        batch_id = _resolve_batch_id(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
        )
        context = Core3RepositoryContext(db=db, project_id=args.project_id, category_code=args.category_code)
        query = CleaningQueryRepository(context)
        summary = query.get_clean_summary(batch_id)
        skus = query.list_clean_skus(batch_id, limit=max(args.limit_skus, 1))
        return {
            "command": "inspect-data-quality",
            "status": "success",
            "batch_id": batch_id,
            "clean_counts": summary["clean_counts"],
            "issue_counts": summary["issue_counts"],
            "review_required": summary["review_required"],
            "market_coverage_summary": summary["preliminary_summary"].get("market_coverage_summary", {}),
            "comment_preliminary_summary": summary["preliminary_summary"].get("comment_preliminary_summary", {}),
            "sample_skus": [
                {
                    "sku_code": sku.sku_code,
                    "quality_status": sku.quality_status,
                    "quality_flags": sku.quality_flags or [],
                    "coverage": sku.coverage_json or {},
                }
                for sku in skus
            ],
        }


def _register_source_batch(db: Session, args: argparse.Namespace) -> dict[str, Any]:
    request = Core3SourceBatchRegisterRequest(
        project_id=args.project_id,
        category_code=args.category_code,
        batch_type=Core3SourceBatchType(args.register_source_batch),
        source_tables=_parse_csv(args.source_tables),
        triggered_by="claude_code_cli",
        note_cn="CLI 初步处理新上传数据：仅为 M01 预处理准备来源批次。",
    )
    result = SourceRegistryRunner(db).register_batch(request)
    db.commit()
    payload = _module_result_payload(result)
    payload["batch_id"] = result.summary_json["batch_id"]
    return payload


def _resolve_batch_id(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
) -> str:
    if batch_id != "latest":
        return batch_id
    stmt = (
        select(entities.Core3SourceBatch)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.category_code == category_code)
        .where(entities.Core3SourceBatch.status.in_(CONSUMABLE_BATCH_STATUSES))
        .order_by(entities.Core3SourceBatch.scan_started_at.desc(), entities.Core3SourceBatch.created_at.desc())
        .limit(1)
    )
    batch = db.execute(stmt).scalars().first()
    if batch is None:
        raise CliError("没有找到可消费的 source batch；请先注册源数据批次。")
    return str(batch.batch_id)


def _resolve_target_skus(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    requested_skus: Sequence[str],
    limit: int | None,
) -> list[str]:
    requested = _unique_values(requested_skus)
    if requested:
        return requested[:limit] if limit else requested

    impacted_stmt = (
        select(entities.Core3SourceImpactedSku.sku_code_candidate)
        .where(entities.Core3SourceImpactedSku.project_id == project_id)
        .where(entities.Core3SourceImpactedSku.category_code == category_code)
        .where(entities.Core3SourceImpactedSku.batch_id == batch_id)
        .where(entities.Core3SourceImpactedSku.needs_recompute.is_(True))
        .order_by(entities.Core3SourceImpactedSku.sku_code_candidate)
    )
    rows = [str(value) for value in db.execute(impacted_stmt).scalars() if value]
    if not rows:
        registry_stmt = (
            select(distinct(entities.Core3SourceRowRegistry.sku_code_candidate))
            .where(entities.Core3SourceRowRegistry.project_id == project_id)
            .where(entities.Core3SourceRowRegistry.category_code == category_code)
            .where(entities.Core3SourceRowRegistry.batch_id == batch_id)
            .where(entities.Core3SourceRowRegistry.sku_code_candidate.is_not(None))
            .order_by(entities.Core3SourceRowRegistry.sku_code_candidate)
        )
        rows = [str(value) for value in db.execute(registry_stmt).scalars() if value]
    rows = _unique_values(rows)
    return rows[:limit] if limit else rows


def _sku_chunks(skus: Sequence[str], chunk_size: int) -> list[tuple[str, ...]]:
    if chunk_size <= 0:
        return [tuple(skus)]
    return [tuple(skus[index : index + chunk_size]) for index in range(0, len(skus), chunk_size)]


def _module_result_payload(result: Any) -> dict[str, Any]:
    return {
        "module_code": _enum_value(result.module_code),
        "status": _enum_value(result.status),
        "input_count": result.input_count,
        "changed_input_count": result.changed_input_count,
        "output_count": result.output_count,
        "warnings": list(result.warnings or []),
        "summary_json": result.summary_json or {},
        "started_at": _datetime_to_iso(result.started_at),
        "finished_at": _datetime_to_iso(result.finished_at),
    }


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _unique_values(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _datetime_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _new_cli_run_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"cli-{prefix}-{timestamp}"


def _print_payload(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    print(_text_payload(payload))


def _text_payload(payload: dict[str, Any]) -> str:
    lines = [
        f"status: {payload.get('status')}",
        f"batch_id: {payload.get('batch_id', '')}",
    ]
    message = payload.get("message_cn")
    if message:
        lines.append(f"message: {message}")
    if payload.get("clean_counts"):
        lines.append(f"clean_counts: {payload['clean_counts']}")
    if payload.get("m01_summary"):
        summary = payload["m01_summary"]
        lines.append(f"clean_counts: {summary.get('clean_counts', {})}")
        lines.append(f"comment_preliminary_summary: {summary.get('comment_preliminary_summary', {})}")
        lines.append(f"market_coverage_summary: {summary.get('market_coverage_summary', {})}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
