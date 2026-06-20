"""Business-level CatForge data operations for local and server-side agents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import entities
from app.schemas.core3_real_data import Core3SourceBatchRegisterRequest
from app.services.core3_real_data.cleaning_repositories import CleaningQueryRepository
from app.services.core3_real_data.cleaning_runner import CleaningQualityRunner
from app.services.core3_real_data.constants import Core3SourceBatchStatus, Core3SourceBatchType
from app.services.core3_real_data.evidence_atom_service import EvidenceAtomRunner
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
        elif args.command == "inspect-sku-quality":
            payload = _inspect_sku_quality(args)
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
        help="Register optional raw changes, clean data, and prepare evidence for analysis.",
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
    prepare.add_argument(
        "--evidence-sku-batch-size",
        type=int,
        default=1,
        help="SKU chunk size for M02 evidence preparation.",
    )
    prepare.add_argument("--skip-evidence", action="store_true", help=argparse.SUPPRESS)
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

    sku_parser = subparsers.add_parser(
        "inspect-sku-quality",
        help="Inspect M01 preliminary cleaning and quality coverage for one SKU.",
    )
    _add_common_project_args(sku_parser)
    sku_parser.add_argument("--batch-id", default="latest")
    sku_parser.add_argument("--sku-code", required=True)
    sku_parser.add_argument("--issue-limit", type=int, default=10)
    return parser


def _add_common_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=argparse.SUPPRESS)
    parser.add_argument("--category-code", default=argparse.SUPPRESS)
    parser.add_argument("--format", choices=("json", "text"), default=argparse.SUPPRESS)


def _prepare_new_data(args: argparse.Namespace) -> dict[str, Any]:
    with SessionLocal() as db:
        batch_id = args.batch_id
        project_id = args.project_id
        category_code = args.category_code
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
                    "evidence_chunk_count": None,
                    "sku_batch_size": args.sku_batch_size,
                    "evidence_sku_batch_size": args.evidence_sku_batch_size,
                    "source_registration_mode": args.register_source_batch,
                    "include_no_change": bool(args.include_no_change),
                    "will_run_modules": ["M00", "M01"] if args.skip_evidence else ["M00", "M01", "M02"],
                    "will_not_run_modules": ["M02", "M05"] if args.skip_evidence else ["M05"],
                },
                "message_cn": "这是数据预处理执行计划，尚未登记源批次，也未写入清洗和证据准备结果。",
            }

        if args.register_source_batch != "none":
            source_registration = _register_source_batch(db, args)
            batch_id = str(source_registration["batch_id"])
        else:
            batch_id, project_id, category_code = _resolve_batch_scope(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
            )

        target_skus = _resolve_target_skus(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            requested_skus=args.sku_code,
            limit=args.limit_skus,
        )
        if not target_skus and not args.allow_full_scan:
            raise CliError(
                f"未找到 batch {batch_id} 的目标 SKU；如确认要全量扫描，请加 --allow-full-scan。"
            )

        chunks = _sku_chunks(target_skus, args.sku_batch_size) if target_skus else [()]
        evidence_chunks = _sku_chunks(target_skus, args.evidence_sku_batch_size) if target_skus else [()]
        plan = {
            "batch_id": batch_id,
            "sku_count": len(target_skus),
            "chunk_count": len(chunks),
            "evidence_chunk_count": len(evidence_chunks) if not args.skip_evidence else 0,
            "sku_batch_size": args.sku_batch_size,
            "evidence_sku_batch_size": args.evidence_sku_batch_size,
            "source_registration_mode": args.register_source_batch,
            "include_no_change": bool(args.include_no_change),
            "will_run_modules": _prepare_run_modules(args.register_source_batch, include_evidence=not args.skip_evidence),
            "will_not_run_modules": ["M02", "M05"] if args.skip_evidence else ["M05"],
            "resolved_project_id": project_id,
            "resolved_category_code": category_code,
        }
        if args.dry_run:
            return {
                "command": "prepare-new-data",
                "status": "dry_run",
                "source_registration": source_registration,
                "plan": plan,
                "message_cn": "这是数据预处理执行计划，尚未写入清洗和证据准备结果。",
            }

        execution_label = args.run_id or _new_cli_run_id("m01")
        run_id = args.run_id
        chunk_results: list[dict[str, Any]] = []
        evidence_chunk_results: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        last_evidence_result: dict[str, Any] | None = None
        runner = CleaningQualityRunner(db)
        for index, chunk in enumerate(chunks, start=1):
            result = runner.run_batch(
                project_id=project_id,
                category_code=category_code,
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

        if last_result and last_result["status"] not in {"failed", "blocked"} and not args.skip_evidence:
            evidence_runner = EvidenceAtomRunner(db)
            evidence_module_run_id = f"{args.module_run_id}-m02" if args.module_run_id else None
            for index, chunk in enumerate(evidence_chunks, start=1):
                result = evidence_runner.run_batch(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=evidence_module_run_id,
                    target_sku_codes=tuple(chunk),
                )
                db.commit()
                db.expunge_all()
                last_evidence_result = _module_result_payload(result)
                evidence_chunk_results.append(
                    {
                        "chunk_index": index,
                        "sku_count": len(chunk),
                        "status": last_evidence_result["status"],
                        "input_count": last_evidence_result["input_count"],
                        "output_count": last_evidence_result["output_count"],
                    }
                )
                if last_evidence_result["status"] in {"failed", "blocked"}:
                    break

        status = "success"
        if last_result and last_result["status"] in {"failed", "blocked"}:
            status = last_result["status"]
        elif last_evidence_result and last_evidence_result["status"] in {"failed", "blocked"}:
            status = last_evidence_result["status"]
        elif last_result and last_result["status"] == "warning":
            status = "warning"
        elif last_evidence_result and last_evidence_result["status"] == "warning":
            status = "warning"

        if args.skip_evidence:
            message_cn = (
                "已完成快速预检：已执行源数据登记和初步清洗过滤，尚未生成分析证据。"
                if args.register_source_batch != "none"
                else "已完成已有批次快速预检：已执行初步清洗过滤，尚未生成分析证据。"
            )
        else:
            message_cn = (
                "已完成数据预处理：已执行源数据登记、初步清洗过滤和分析证据准备，数据已可进入事实分析。"
                if args.register_source_batch != "none"
                else "已完成已有批次数据预处理：已执行初步清洗过滤和分析证据准备，数据已可进入事实分析。"
            )

        return {
            "command": "prepare-new-data",
            "status": status,
            "batch_id": batch_id,
            "project_id": project_id,
            "category_code": category_code,
            "execution_label": execution_label,
            "source_registration": source_registration,
            "plan": plan,
            "processed_chunks": chunk_results,
            "processed_evidence_chunks": evidence_chunk_results,
            "m01_summary": last_result["summary_json"] if last_result else {},
            "m02_summary": last_evidence_result["summary_json"] if last_evidence_result else {},
            "message_cn": message_cn,
        }


def _inspect_data_quality(args: argparse.Namespace) -> dict[str, Any]:
    with SessionLocal() as db:
        batch_id, project_id, category_code = _resolve_batch_scope(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
        )
        context = Core3RepositoryContext(db=db, project_id=project_id, category_code=category_code)
        query = CleaningQueryRepository(context)
        summary = query.get_clean_summary(batch_id)
        skus = query.list_clean_skus(batch_id, limit=max(args.limit_skus, 1))
        return {
            "command": "inspect-data-quality",
            "status": "success",
            "batch_id": batch_id,
            "project_id": project_id,
            "category_code": category_code,
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


def _inspect_sku_quality(args: argparse.Namespace) -> dict[str, Any]:
    sku_code = str(args.sku_code).strip()
    if not sku_code:
        raise CliError("请提供有效的 --sku-code。")

    with SessionLocal() as db:
        batch_id, project_id, category_code = _resolve_batch_scope(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
        )
        sku = _get_clean_sku(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            sku_code=sku_code,
        )
        if sku is None:
            return {
                "command": "inspect-sku-quality",
                "status": "not_found",
                "found": False,
                "batch_id": batch_id,
                "project_id": project_id,
                "category_code": category_code,
                "sku_code": sku_code,
                "message_cn": f"批次 {batch_id} 中未找到 SKU {sku_code} 的 M01 清洗结果。",
            }

        return {
            "command": "inspect-sku-quality",
            "status": "success",
            "found": True,
            "batch_id": batch_id,
            "project_id": project_id,
            "category_code": category_code,
            "sku_code": sku_code,
            "sku": {
                "sku_code": sku.sku_code,
                "model_name": sku.model_name,
                "brand_name": sku.brand_name,
                "category_name": sku.category_name,
                "source_tables": sku.source_tables or [],
                "quality_status": sku.quality_status,
                "quality_flags": sku.quality_flags or [],
                "review_required": bool(sku.review_required),
                "review_status": sku.review_status,
            },
            "row_counts": _sku_row_counts(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                sku_code=sku_code,
            ),
            "market_summary": _sku_market_summary(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                sku_code=sku_code,
                coverage=sku.coverage_json or {},
            ),
            "attribute_summary": _sku_attribute_summary(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                sku_code=sku_code,
                coverage=sku.coverage_json or {},
            ),
            "claim_summary": _sku_claim_summary(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                sku_code=sku_code,
            ),
            "comment_summary": _sku_comment_summary(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                sku_code=sku_code,
                coverage=sku.coverage_json or {},
            ),
            "quality_issue_summary": _sku_quality_issue_summary(
                db,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                sku_code=sku_code,
                issue_limit=args.issue_limit,
            ),
            "stored_coverage": sku.coverage_json or {},
            "message_cn": f"已读取 SKU {sku_code} 在批次 {batch_id} 的 M01 清洗摘要。",
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
    return _resolve_batch_scope(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
    )[0]


def _resolve_batch_scope(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
) -> tuple[str, str, str]:
    if batch_id != "latest":
        batch = _find_source_batch_by_id(db, batch_id)
        if batch is None:
            return batch_id, project_id, category_code
        return str(batch.batch_id), str(batch.project_id), str(batch.category_code)

    batch = _find_latest_source_batch(db, project_id=project_id, category_code=category_code)
    if batch is None:
        batch = _find_latest_source_batch(db, project_id=None, category_code=category_code)
    if batch is None:
        raise CliError("没有找到可消费的 source batch；请先注册源数据批次。")
    return str(batch.batch_id), str(batch.project_id), str(batch.category_code)


def _find_source_batch_by_id(db: Session, batch_id: str) -> entities.Core3SourceBatch | None:
    stmt = select(entities.Core3SourceBatch).where(entities.Core3SourceBatch.batch_id == batch_id).limit(1)
    return db.execute(stmt).scalars().first()


def _find_latest_source_batch(
    db: Session,
    *,
    project_id: str | None,
    category_code: str,
) -> entities.Core3SourceBatch | None:
    stmt = select(entities.Core3SourceBatch).where(
        entities.Core3SourceBatch.status.in_(CONSUMABLE_BATCH_STATUSES)
    )
    if project_id is not None:
        stmt = stmt.where(entities.Core3SourceBatch.project_id == project_id)
    if category_code:
        stmt = stmt.where(entities.Core3SourceBatch.category_code == category_code)
    stmt = stmt.order_by(entities.Core3SourceBatch.scan_started_at.desc(), entities.Core3SourceBatch.created_at.desc()).limit(1)
    batch = db.execute(stmt).scalars().first()
    return batch


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


def _get_clean_sku(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> entities.Core3CleanSku | None:
    stmt = (
        select(entities.Core3CleanSku)
        .where(entities.Core3CleanSku.project_id == project_id)
        .where(entities.Core3CleanSku.category_code == category_code)
        .where(entities.Core3CleanSku.batch_id == batch_id)
        .where(entities.Core3CleanSku.sku_code == sku_code)
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def _sku_row_counts(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> dict[str, int]:
    return {
        "sku": _count_sku_rows(db, entities.Core3CleanSku, project_id, category_code, batch_id, sku_code),
        "market": _count_sku_rows(db, entities.Core3CleanMarketWeekly, project_id, category_code, batch_id, sku_code),
        "attribute": _count_sku_rows(db, entities.Core3CleanAttribute, project_id, category_code, batch_id, sku_code),
        "claim": _count_sku_rows(db, entities.Core3CleanClaim, project_id, category_code, batch_id, sku_code),
        "claim_sentence": _count_sku_rows(
            db,
            entities.Core3CleanClaimSentence,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "comment": _count_sku_rows(db, entities.Core3CleanComment, project_id, category_code, batch_id, sku_code),
        "comment_sentence": _count_sku_rows(
            db,
            entities.Core3CleanCommentSentence,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "comment_dimension": _count_sku_rows(
            db,
            entities.Core3CleanCommentDimension,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "quality_issue": _count_sku_rows(
            db,
            entities.Core3DataQualityIssue,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
    }


def _sku_market_summary(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    model = entities.Core3CleanMarketWeekly
    min_week, max_week, min_period, max_period, distinct_week_count, sales_volume, sales_amount = db.execute(
        _apply_sku_filters(
            select(
                func.min(model.period_week_index),
                func.max(model.period_week_index),
                func.min(model.period_raw),
                func.max(model.period_raw),
                func.count(distinct(model.period_raw)),
                func.sum(model.sales_volume),
                func.sum(model.sales_amount),
            ),
            model,
            project_id,
            category_code,
            batch_id,
            sku_code,
        )
    ).one()
    weekly_coverage = ((coverage.get("market") or {}).get("weekly_coverage") or {})
    return {
        "row_count": _count_sku_rows(db, model, project_id, category_code, batch_id, sku_code),
        "period_week_index_min": min_week,
        "period_week_index_max": max_week,
        "period_raw_min": min_period,
        "period_raw_max": max_period,
        "distinct_week_count": int(distinct_week_count or 0),
        "sales_volume_sum": sales_volume,
        "sales_amount_sum": sales_amount,
        "platform_counts": _group_counts(
            db,
            model,
            model.platform_type,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "price_check_counts": _group_counts(
            db,
            model,
            model.price_check_status,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "quality_status_counts": _group_counts(
            db,
            model,
            model.quality_status,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "review_required_count": _count_sku_rows_where(
            db,
            model,
            project_id,
            category_code,
            batch_id,
            sku_code,
            model.review_required.is_(True),
        ),
        "weekly_coverage": weekly_coverage,
    }


def _sku_attribute_summary(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    model = entities.Core3CleanAttribute
    coverage_attribute = coverage.get("attribute") or {}
    return {
        "row_count": _count_sku_rows(db, model, project_id, category_code, batch_id, sku_code),
        "unknown_count": coverage_attribute.get("unknown_count"),
        "value_presence_counts": _group_counts(
            db,
            model,
            model.value_presence,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "quality_status_counts": _group_counts(
            db,
            model,
            model.quality_status,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "review_required_count": _count_sku_rows_where(
            db,
            model,
            project_id,
            category_code,
            batch_id,
            sku_code,
            model.review_required.is_(True),
        ),
    }


def _sku_claim_summary(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> dict[str, Any]:
    model = entities.Core3CleanClaim
    return {
        "row_count": _count_sku_rows(db, model, project_id, category_code, batch_id, sku_code),
        "sentence_count": _count_sku_rows(
            db,
            entities.Core3CleanClaimSentence,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "text_presence_counts": _group_counts(
            db,
            model,
            model.claim_text_presence,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "quality_status_counts": _group_counts(
            db,
            model,
            model.quality_status,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "review_required_count": _count_sku_rows_where(
            db,
            model,
            project_id,
            category_code,
            batch_id,
            sku_code,
            model.review_required.is_(True),
        ),
    }


def _sku_comment_summary(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    model = entities.Core3CleanComment
    row_count = _count_sku_rows(db, model, project_id, category_code, batch_id, sku_code)
    low_value_count = _count_sku_rows_where(
        db,
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        model.low_value_flag.is_(True),
    )
    candidate_count = _count_sku_rows_where(
        db,
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        model.low_value_flag.is_(False),
    )
    service_condition = model.low_value_reason.contains("服务履约评价")
    service_count = _count_sku_rows_where(
        db,
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        service_condition,
    )
    service_after_low_value_count = _count_sku_rows_where(
        db,
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        model.low_value_flag.is_(False),
        service_condition,
    )
    empty_or_default_count = _count_sku_rows_where(
        db,
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        model.low_value_reason.contains("默认或空评价"),
    )
    duplicate_text_row_count = _count_sku_rows_where(
        db,
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        model.duplicate_group_key.is_not(None),
    )
    distinct_comment_id_count = _count_distinct_sku_values(
        db,
        model,
        model.comment_id,
        project_id,
        category_code,
        batch_id,
        sku_code,
    )
    duplicate_text_group_count = _count_distinct_sku_values(
        db,
        model,
        model.duplicate_group_key,
        project_id,
        category_code,
        batch_id,
        sku_code,
    )
    dimension_model = entities.Core3CleanCommentDimension
    dimension_count = _count_sku_rows(db, dimension_model, project_id, category_code, batch_id, sku_code)
    dimension_available_count = _count_sku_rows_where(
        db,
        dimension_model,
        project_id,
        category_code,
        batch_id,
        sku_code,
        dimension_model.dimension_available.is_(True),
    )
    coverage_comment = coverage.get("comment") or {}
    return {
        "raw_row_count": row_count,
        "low_value_comment_count": low_value_count,
        "low_value_comment_rate": _rate(low_value_count, row_count),
        "candidate_after_low_value_count": candidate_count,
        "service_candidate_count": service_count,
        "service_candidate_rate": _rate(service_count, row_count),
        "service_candidate_after_low_value_count": service_after_low_value_count,
        "service_candidate_after_low_value_rate": _rate(service_after_low_value_count, row_count),
        "service_candidate_not_blocked": service_after_low_value_count > 0,
        "empty_or_default_comment_count": empty_or_default_count,
        "duplicate_text_group_count": duplicate_text_group_count,
        "duplicate_text_row_count": duplicate_text_row_count,
        "distinct_comment_id_count": distinct_comment_id_count,
        "sentence_count": _count_sku_rows(
            db,
            entities.Core3CleanCommentSentence,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "dimension_count": dimension_count,
        "dimension_available_count": dimension_available_count,
        "sentiment_counts": _group_counts(
            db,
            model,
            model.sentiment_clean,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "quality_status_counts": _group_counts(
            db,
            model,
            model.quality_status,
            project_id,
            category_code,
            batch_id,
            sku_code,
        ),
        "review_required_count": _count_sku_rows_where(
            db,
            model,
            project_id,
            category_code,
            batch_id,
            sku_code,
            model.review_required.is_(True),
        ),
        "stored_preliminary_filter": coverage_comment.get("preliminary_filter") or {},
    }


def _sku_quality_issue_summary(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    issue_limit: int,
) -> dict[str, Any]:
    model = entities.Core3DataQualityIssue
    counts: dict[str, Any] = {
        "total": 0,
        "info": 0,
        "warning": 0,
        "error": 0,
        "review_required": 0,
        "by_type": {},
        "by_clean_table": {},
    }
    stmt = _apply_sku_filters(
        select(model.severity, model.issue_type, model.clean_table, model.review_required, func.count()).group_by(
            model.severity,
            model.issue_type,
            model.clean_table,
            model.review_required,
        ),
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
    )
    by_type: dict[str, int] = {}
    by_clean_table: dict[str, int] = {}
    for severity, issue_type, clean_table, review_required, count in db.execute(stmt).all():
        normalized_count = int(count)
        counts["total"] += normalized_count
        if severity in {"info", "warning", "error"}:
            counts[str(severity)] += normalized_count
        if review_required:
            counts["review_required"] += normalized_count
        if issue_type:
            by_type[str(issue_type)] = by_type.get(str(issue_type), 0) + normalized_count
        if clean_table:
            by_clean_table[str(clean_table)] = by_clean_table.get(str(clean_table), 0) + normalized_count
    counts["by_type"] = by_type
    counts["by_clean_table"] = by_clean_table
    normalized_limit = max(int(issue_limit), 0)
    sample_stmt = _apply_sku_filters(
        select(model.issue_type, model.severity, model.clean_table, model.issue_detail, model.review_required)
        .order_by(model.created_at, model.issue_id)
        .limit(normalized_limit),
        model,
        project_id,
        category_code,
        batch_id,
        sku_code,
    )
    counts["sample_issues"] = [
        {
            "issue_type": issue_type,
            "severity": severity,
            "clean_table": clean_table,
            "issue_detail": issue_detail,
            "review_required": bool(review_required),
        }
        for issue_type, severity, clean_table, issue_detail, review_required in db.execute(sample_stmt).all()
    ]
    return counts


def _count_sku_rows(
    db: Session,
    model_cls: Any,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> int:
    return _count_sku_rows_where(db, model_cls, project_id, category_code, batch_id, sku_code)


def _count_sku_rows_where(
    db: Session,
    model_cls: Any,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    *conditions: Any,
) -> int:
    stmt = _apply_sku_filters(
        select(func.count()).select_from(model_cls),
        model_cls,
        project_id,
        category_code,
        batch_id,
        sku_code,
    )
    for condition in conditions:
        stmt = stmt.where(condition)
    return int(db.execute(stmt).scalar_one())


def _count_distinct_sku_values(
    db: Session,
    model_cls: Any,
    column: Any,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> int:
    stmt = _apply_sku_filters(
        select(func.count(distinct(column))).select_from(model_cls),
        model_cls,
        project_id,
        category_code,
        batch_id,
        sku_code,
    ).where(column.is_not(None))
    return int(db.execute(stmt).scalar_one())


def _group_counts(
    db: Session,
    model_cls: Any,
    column: Any,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> dict[str, int]:
    stmt = _apply_sku_filters(
        select(column, func.count()).select_from(model_cls).group_by(column),
        model_cls,
        project_id,
        category_code,
        batch_id,
        sku_code,
    )
    return {str(value) if value is not None else "unknown": int(count) for value, count in db.execute(stmt).all()}


def _apply_sku_filters(
    stmt: Any,
    model_cls: Any,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
) -> Any:
    return (
        stmt.where(model_cls.project_id == project_id)
        .where(model_cls.category_code == category_code)
        .where(model_cls.batch_id == batch_id)
        .where(model_cls.sku_code == sku_code)
    )


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _sku_chunks(skus: Sequence[str], chunk_size: int) -> list[tuple[str, ...]]:
    if chunk_size <= 0:
        return [tuple(skus)]
    return [tuple(skus[index : index + chunk_size]) for index in range(0, len(skus), chunk_size)]


def _prepare_run_modules(register_source_batch: str, *, include_evidence: bool) -> list[str]:
    modules = ["M00", "M01"] if register_source_batch != "none" else ["M01"]
    if include_evidence:
        modules.append("M02")
    return modules


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
