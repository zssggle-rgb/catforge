"""Execution CLI for CatForge data-preparation and fact-profile jobs.

This module is intentionally small and agent-friendly. It exposes write actions
that natural-language agents can call without asking users to know module codes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_PARSER_VERSION,
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_PARSER_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.m03b_param_profile_service import M03BRunner


DEFAULT_PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_CATEGORY_CODE = "TV"
LATEST_BATCH = "latest"

PRODUCT_CATEGORY_CONFIGS = {
    "TV": {
        "label_cn": "彩电",
        "sku_code_prefix": "TV",
        "taxonomy_version": CORE3_M03B_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_PARSER_VERSION,
        "rule_version": CORE3_M03B_RULE_VERSION,
    },
    "AC": {
        "label_cn": "空调",
        "sku_code_prefix": "AC",
        "taxonomy_version": CORE3_M03B_AC_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_AC_PARSER_VERSION,
        "rule_version": CORE3_M03B_AC_RULE_VERSION,
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
            elif args.command == "ask":
                result = answer_natural_language(
                    db,
                    question=" ".join(args.question),
                    project_id=args.project_id,
                    source_category_code=args.category_code,
                    batch_id=args.batch_id,
                    product_category=args.product_category,
                    force_rebuild=args.force_rebuild,
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

    ask = subparsers.add_parser("ask", help="Route a natural-language execution request.")
    add_common_args(ask)
    add_product_category_arg(ask)
    ask.add_argument("question", nargs="+", help="Natural-language execution request.")
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
) -> dict[str, Any]:
    resolved_product_category = resolve_product_category(product_category, question=question)
    if not should_run_param_profile(question):
        raise CatForgePipelineError("当前执行 CLI 只支持生成/重跑 SKU 参数画像。请说明要生成或重新生成参数画像。")
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
    lines = [
        f"{label} SKU 参数画像生成完成：status={result['module_status']}",
        f"批次：{result['batch_id']}；输入 evidence：{result['input_count']}；输出：{result['output_count']}；前缀：{result['sku_code_prefix']}",
        f"taxonomy={result['taxonomy_version']}；rule={result['rule_version']}",
    ]
    if result.get("warnings"):
        lines.append("warnings: " + ", ".join(result["warnings"]))
    summary = result.get("summary") or {}
    if isinstance(summary, dict):
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
