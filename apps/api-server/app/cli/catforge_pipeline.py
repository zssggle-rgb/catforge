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
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.m03b_param_profile_service import M03BRunner
from app.services.core3_real_data.m04c_claim_fact_profile_service import INPUT_SOURCE_AUTO, M04CRunner
from app.services.core3_real_data.market_profile_runner import MarketProfileRunner


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
        "claim_taxonomy_version": CORE3_M04C_TV_TAXONOMY_VERSION,
        "claim_rule_version": CORE3_M04C_TV_RULE_VERSION,
    },
    "AC": {
        "label_cn": "空调",
        "sku_code_prefix": "AC",
        "taxonomy_version": CORE3_M03B_AC_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_AC_PARSER_VERSION,
        "rule_version": CORE3_M03B_AC_RULE_VERSION,
        "claim_taxonomy_version": None,
        "claim_rule_version": None,
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

    run_claim = subparsers.add_parser("run-claim-profile", help="Generate or rerun SKU claim fact profiles for a product category.")
    add_common_args(run_claim)
    add_product_category_arg(run_claim, default="tv", allow_auto=False)
    run_claim.add_argument("--input-source", choices=("auto", "evidence", "clean", "raw"), default=INPUT_SOURCE_AUTO, help="Claim input source. auto prefers M02 evidence, then M01 clean claims, then raw selling_points_data.")
    run_claim.add_argument("--force-rebuild", action="store_true", help="Replace same business-key outputs if hashes changed.")
    add_format_arg(run_claim)

    run_market = subparsers.add_parser("run-market-profile", help="Generate or rerun SKU market profiles and comparable-pool baselines.")
    add_common_args(run_market)
    run_market.add_argument("--analysis-window", action="append", choices=("full_observed_window", "latest_week", "recent_4w", "recent_8w", "recent_12w"), help="Analysis window to run. Repeat for multiple windows. Default runs all M07 windows.")
    run_market.add_argument("--sku-code", action="append", help="Optional SKU scope. Repeat to run selected SKUs only.")
    add_format_arg(run_market)

    ask = subparsers.add_parser("ask", help="Route a natural-language execution request.")
    add_common_args(ask)
    add_product_category_arg(ask)
    ask.add_argument("question", nargs="+", help="Natural-language execution request.")
    ask.add_argument("--input-source", choices=("auto", "evidence", "clean", "raw"), default=INPUT_SOURCE_AUTO, help="Claim input source when the natural-language request routes to claim profile generation.")
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
) -> dict[str, Any]:
    resolved_product_category = resolve_product_category(product_category, question=question)
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
        raise CatForgePipelineError("当前执行 CLI 只支持生成/重跑 SKU 参数画像或卖点事实画像。请说明要生成或重新生成哪类画像。")
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


def run_market_profile(
    db: Session,
    *,
    project_id: str,
    source_category_code: str,
    batch_id: str,
    sku_scope: Sequence[str] = (),
    analysis_windows: Sequence[str] = (),
) -> dict[str, Any]:
    resolved_batch_id = resolve_source_batch_id(db, project_id, source_category_code, batch_id)
    module_result = MarketProfileRunner(db).run_batch(
        project_id=project_id,
        category_code=source_category_code,
        batch_id=resolved_batch_id,
        rule_version=CORE3_M07_RULE_VERSION,
        price_band_rule_version=CORE3_M07_PRICE_BAND_RULE_VERSION,
        pool_rule_version=CORE3_M07_POOL_RULE_VERSION,
        sku_scope=tuple(sku_scope),
        analysis_windows=tuple(analysis_windows),
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
        "product_category": "TV",
        "product_category_label_cn": "彩电",
        "batch_id": resolved_batch_id,
        "sku_scope": list(sku_scope),
        "analysis_windows": list(analysis_windows) or "all",
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


def should_run_market_profile(question: str) -> bool:
    normalized = normalize_token(question)
    if "市场画像" in question:
        return any(word in normalized for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算", "量价", "市场画像"))
    return any(word in normalized for word in ("量价画像", "市场量价", "价格区间", "尺寸区间")) and any(
        word in normalized for word in ("生成", "重跑", "重新", "更新", "执行", "跑", "计算")
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
    is_market_profile = isinstance(summary, dict) and "market_profile_count" in summary
    if is_market_profile:
        job_name = "SKU 市场画像"
        input_label = "输入周销量价"
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
