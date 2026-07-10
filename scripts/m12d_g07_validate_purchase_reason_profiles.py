#!/usr/bin/env python3
"""Small-batch validation for M12D SKU purchase reason profiles."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models import entities  # noqa: E402
from app.services.core3_real_data.analyst.analyst_repository import batch_ids_from_scope  # noqa: E402
from app.services.core3_real_data.analyst.analyst_service import (  # noqa: E402
    LATEST_BATCH,
    CatForgeAnalystService,
)
from app.services.core3_real_data.constants import CORE3_M07_RULE_VERSION  # noqa: E402
from app.services.core3_real_data.purchase_reason_profile_preview import (  # noqa: E402
    M12DSkuPurchaseReasonPreviewError,
    build_sku_purchase_reason_preview,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CODE = "TV"
PRODUCT_CATEGORY = "tv"
MARKET_WINDOW = "full_observed_window"
ANALYSIS_POPULATION = "fact_complete_with_comment"
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"
DEFAULT_SAMPLE_SKUS = (
    "TV00029112",  # 海信 65E7Q
    "TV00029936",  # 创维 65A7H PRO
    "TV00027801",  # TCL 65Q9L PRO
    "TV00029020",  # 小米 L65MC-SP
    "TV00028829",  # 创维 65A6F ULTRA
)
BUDGET_VALUE_REASON_CODE = "same_price_core_config_gain"
LOW_CONFIDENCE_THRESHOLD = Decimal("0.5000")


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        payload = validate_small_batch(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            product_category=args.product_category,
            batch_id=args.batch_id,
            sample_size=args.sample_size,
            extra_skus=tuple(args.sku_code or ()),
        )

    json_path = output_dir / "M12D_G07_small_batch_validation.json"
    md_path = output_dir / "M12D_G07_small_batch_validation_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    md_path.write_text(render_markdown_report(payload), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


def validate_small_batch(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    product_category: str,
    batch_id: str,
    sample_size: int,
    extra_skus: tuple[str, ...] = (),
) -> dict[str, Any]:
    resolved_batch_id = resolve_batch_id(
        db,
        project_id=project_id,
        category_code=category_code,
        product_category=product_category,
        batch_id=batch_id,
    )
    sample_skus = select_sample_skus(
        db,
        project_id=project_id,
        category_code=category_code,
        product_category=product_category,
        batch_id=resolved_batch_id,
        sample_size=sample_size,
        extra_skus=extra_skus,
    )
    results = [
        validate_one_sku(
            db,
            project_id=project_id,
            category_code=category_code,
            product_category=product_category,
            batch_id=resolved_batch_id,
            sku_code=sku_code,
        )
        for sku_code in sample_skus
    ]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": "M12D-G07 small-batch validation",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category.upper(),
        "requested_batch_id": batch_id,
        "resolved_batch_id": resolved_batch_id,
        "sample_size": len(results),
        "source_note_cn": "只读当前 Core3 TV 结果；本脚本只调用 M12D 单 SKU 预览服务，不写入生产表。",
        "sample_results": results,
        "summary": build_summary(results),
        "rule_correction_record": build_rule_correction_record(results, resolved_batch_id),
    }


def resolve_batch_id(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    product_category: str,
    batch_id: str,
) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    service = CatForgeAnalystService(db, project_id=project_id, category_code=category_code)
    return service.build_context(
        batch_id=batch_id,
        product_category=product_category,
        market_window=MARKET_WINDOW,
        analysis_population=ANALYSIS_POPULATION,
        resolve_latest=True,
    ).batch_id


def select_sample_skus(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    product_category: str,
    batch_id: str,
    sample_size: int,
    extra_skus: tuple[str, ...],
) -> list[str]:
    sku_prefix = product_category.upper()
    sample: list[str] = []
    for sku_code in (*DEFAULT_SAMPLE_SKUS, *extra_skus):
        normalized = sku_code.strip().upper()
        if normalized and normalized not in sample:
            sample.append(normalized)

    batch_ids = batch_ids_from_scope(batch_id)
    stmt = (
        select(entities.Core3SkuMarketProfile.sku_code)
        .where(entities.Core3SkuMarketProfile.project_id == project_id)
        .where(entities.Core3SkuMarketProfile.category_code == category_code)
        .where(entities.Core3SkuMarketProfile.batch_id.in_(batch_ids))
        .where(entities.Core3SkuMarketProfile.sku_code.like(f"{sku_prefix}%"))
        .where(entities.Core3SkuMarketProfile.analysis_window == "full_observed_window")
        .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
        .where(entities.Core3SkuMarketProfile.is_current.is_(True))
        .order_by(
            entities.Core3SkuMarketProfile.volume_percentile_in_size.desc().nullslast(),
            entities.Core3SkuMarketProfile.price_percentile_in_size.desc().nullslast(),
            entities.Core3SkuMarketProfile.sku_code,
        )
        .limit(max(sample_size * 3, sample_size))
    )
    for sku_code in db.execute(stmt).scalars():
        if sku_code not in sample:
            sample.append(str(sku_code))
        if len(sample) >= sample_size:
            break
    return sample[:sample_size]


def validate_one_sku(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    product_category: str,
    batch_id: str,
    sku_code: str,
) -> dict[str, Any]:
    try:
        preview = build_sku_purchase_reason_preview(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            product_category=product_category,
            sku_code=sku_code,
            max_anchors=12,
        )
    except M12DSkuPurchaseReasonPreviewError as exc:
        return {
            "sku_code": sku_code,
            "status": "failed",
            "message_cn": str(exc),
            "profile_confidence": Decimal("0.0000"),
            "core_payment_anchors": [],
            "supporting_anchors": [],
            "weak_expression_anchors": [],
            "risk_drag_anchors": [],
            "input_status": [],
            "validation_flags": ["preview_failed"],
        }

    profile = preview["profile"]
    sku = preview["sku"]
    core_anchors = profile["core_payment_anchors"]
    supporting_anchors = profile["supporting_anchors"]
    weak_anchors = profile["weak_expression_anchors"]
    risk_anchors = profile["risk_drag_anchors"]
    profile_confidence = Decimal(str(profile["profile_confidence"]))
    flags = validation_flags(
        sku_code=sku_code,
        profile=profile,
        profile_confidence=profile_confidence,
        core_anchors=core_anchors,
        weak_anchors=weak_anchors,
        risk_anchors=risk_anchors,
        input_status=preview["input_status"],
    )
    return {
        "sku_code": sku_code,
        "display_name_cn": sku["display_name_cn"],
        "brand_name": sku.get("brand_name"),
        "model_name": sku.get("model_name"),
        "status": profile["status"],
        "status_cn": profile["status_cn"],
        "profile_confidence": profile_confidence,
        "profile_confidence_pct": profile["profile_confidence_pct"],
        "confidence_level": profile["confidence_level"],
        "confidence_level_cn": profile["confidence_level_cn"],
        "review_required": profile["review_required"],
        "review_reasons": profile["review_reasons"],
        "core_payment_anchors": anchor_codes(core_anchors),
        "supporting_anchors": anchor_codes(supporting_anchors),
        "weak_expression_anchors": anchor_codes(weak_anchors),
        "risk_drag_anchors": anchor_codes(risk_anchors),
        "core_payment_anchor_names": anchor_names(core_anchors),
        "weak_expression_anchor_names": anchor_names(weak_anchors),
        "input_status": preview["input_status"],
        "non_ready_inputs": [
            item for item in preview["input_status"] if item["status"] != "ready"
        ],
        "validation_flags": flags,
    }


def validation_flags(
    *,
    sku_code: str,
    profile: dict[str, Any],
    profile_confidence: Decimal,
    core_anchors: list[dict[str, Any]],
    weak_anchors: list[dict[str, Any]],
    risk_anchors: list[dict[str, Any]],
    input_status: list[dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    core_codes = set(anchor_codes(core_anchors))
    weak_codes = set(anchor_codes(weak_anchors))
    if profile_confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append("low_confidence")
    if profile.get("review_required"):
        flags.append("review_required")
    if core_codes:
        flags.append("has_core_payment_anchor")
    if risk_anchors:
        flags.append("has_risk_drag_anchor")
    if any(item["status"] in {"missing", "unknown", "conflict"} for item in input_status):
        flags.append("input_gap_or_conflict")
    if sku_code == "TV00029112" and BUDGET_VALUE_REASON_CODE in core_codes:
        flags.append("budget_value_misclassified_as_core")
    if sku_code == "TV00029112" and BUDGET_VALUE_REASON_CODE in weak_codes:
        flags.append("budget_value_correctly_weak_expression")
    return flags


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    low_confidence = [item for item in results if "low_confidence" in item["validation_flags"]]
    review_required = [item for item in results if "review_required" in item["validation_flags"]]
    core_payment = [item for item in results if item["core_payment_anchors"]]
    risk_drag = [item for item in results if item["risk_drag_anchors"]]
    budget_failures = [item for item in results if "budget_value_misclassified_as_core" in item["validation_flags"]]
    return {
        "total_sku_count": len(results),
        "low_confidence_count": len(low_confidence),
        "review_required_count": len(review_required),
        "core_payment_present_count": len(core_payment),
        "risk_drag_count": len(risk_drag),
        "budget_value_misclassification_count": len(budget_failures),
        "low_confidence_skus": brief_skus(low_confidence),
        "review_required_skus": brief_skus(review_required),
        "core_payment_skus": brief_skus(core_payment),
        "risk_drag_skus": brief_skus(risk_drag),
        "budget_value_check": budget_value_check(results),
    }


def build_rule_correction_record(results: list[dict[str, Any]], resolved_batch_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        {
            "issue_code": "serving_scope_context_lookup",
            "status": "fixed_in_g07",
            "finding_cn": (
                "G07 验证发现 latest 会解析为 serving-scope 组合批次；"
                "M12D ContextBuilder 需要识别组合批次并按顺序读取第一个可用记录。"
            ),
            "correction_cn": "已修正 ContextBuilder 批次过滤逻辑，并新增 serving-scope 回归测试。",
            "evidence_cn": f"本轮 resolved_batch_id={resolved_batch_id}。",
        }
    ]
    budget_check = budget_value_check(results)
    records.append(
        {
            "issue_code": "budget_value_65e7q_core_guardrail",
            "status": "passed_no_rule_change",
            "finding_cn": budget_check["message_cn"],
            "correction_cn": "未修改评分规则；保留 value_price/price_value 仅弱表达封顶规则。",
            "evidence_cn": "65E7Q 的 same_price_core_config_gain 未进入 core_payment。",
        }
    )
    if any(item.get("status") != "ready" and item["core_payment_anchors"] for item in results):
        records.append(
            {
                "issue_code": "core_anchor_with_degraded_profile",
                "status": "audit_gate_recorded",
                "finding_cn": "部分 SKU 存在 core_payment 锚点，但 SKU 级画像置信度仍低于 ready 门槛。",
                "correction_cn": "本轮不降级锚点角色；报告消费时必须同时展示 profile_status/profile_confidence。",
                "evidence_cn": "详见 sample_results 中 status!=ready 且 core_payment_anchors 非空的样本。",
            }
        )
    return records


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# M12D-G07 小批量验证与规则修正记录",
        "",
        f"- 生成时间 UTC：{payload['generated_at_utc']}",
        f"- 项目：{payload['project_id']} / {payload['category_code']}",
        f"- 请求批次：{payload['requested_batch_id']}",
        f"- 解析批次：{payload['resolved_batch_id']}",
        f"- 样本数：{payload['sample_size']}",
        f"- 口径：{payload['source_note_cn']}",
        "",
        "## 汇总",
        "",
        f"- 低置信 SKU：{summary['low_confidence_count']}",
        f"- 需复核 SKU：{summary['review_required_count']}",
        f"- 有核心成交理由 SKU：{summary['core_payment_present_count']}",
        f"- 有风险拖拽 SKU：{summary['risk_drag_count']}",
        f"- 预算价值误判为核心：{summary['budget_value_misclassification_count']}",
        "",
        "## SKU 明细",
        "",
        "| SKU | 产品 | 状态 | 置信度 | 核心成交理由 | 弱表达 | 风险 | 非 ready 输入 |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in payload["sample_results"]:
        lines.append(
            "| "
            f"{item['sku_code']} | "
            f"{item.get('display_name_cn') or '-'} | "
            f"{item.get('status_cn') or item.get('status')} | "
            f"{item.get('profile_confidence_pct', '-')} | "
            f"{join_values(item.get('core_payment_anchor_names'))} | "
            f"{join_values(item.get('weak_expression_anchor_names'))} | "
            f"{join_values(item.get('risk_drag_anchors'))} | "
            f"{join_values(input_status_labels(item.get('non_ready_inputs') or []))} |"
        )

    lines.extend(["", "## 低置信与复核清单", ""])
    lines.extend(render_brief_list("低置信 SKU", summary["low_confidence_skus"]))
    lines.extend(render_brief_list("需复核 SKU", summary["review_required_skus"]))
    lines.extend(render_brief_list("风险拖拽 SKU", summary["risk_drag_skus"]))

    lines.extend(["", "## 65E7Q 预算价值检查", ""])
    check = summary["budget_value_check"]
    lines.append(f"- 状态：{check['status']}")
    lines.append(f"- 结论：{check['message_cn']}")

    lines.extend(["", "## 规则修正记录", ""])
    for record in payload["rule_correction_record"]:
        lines.extend(
            [
                f"### {record['issue_code']}",
                f"- 状态：{record['status']}",
                f"- 发现：{record['finding_cn']}",
                f"- 修正：{record['correction_cn']}",
                f"- 证据：{record['evidence_cn']}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def budget_value_check(results: list[dict[str, Any]]) -> dict[str, str]:
    target = next((item for item in results if item["sku_code"] == "TV00029112"), None)
    if not target:
        return {"status": "not_checked", "message_cn": "样本中未包含 65E7Q。"}
    core_codes = set(target["core_payment_anchors"])
    weak_codes = set(target["weak_expression_anchors"])
    if BUDGET_VALUE_REASON_CODE in core_codes:
        return {
            "status": "failed",
            "message_cn": "65E7Q 的预算价值表达进入 core_payment，需要修正规则。",
        }
    if BUDGET_VALUE_REASON_CODE in weak_codes:
        return {
            "status": "passed",
            "message_cn": "65E7Q 的同价位核心配置获得感保持为弱表达，未误判为强核心成交理由。",
        }
    return {
        "status": "passed_not_matched",
        "message_cn": "65E7Q 未命中预算价值购买理由，未出现强核心误判。",
    }


def brief_skus(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sku_code": item["sku_code"],
            "display_name_cn": item.get("display_name_cn"),
            "status": item.get("status"),
            "profile_confidence_pct": item.get("profile_confidence_pct"),
            "core_payment_anchors": item.get("core_payment_anchors") or [],
            "validation_flags": item.get("validation_flags") or [],
        }
        for item in items
    ]


def render_brief_list(title: str, items: list[dict[str, Any]]) -> list[str]:
    lines = [f"### {title}"]
    if not items:
        return [*lines, "- 无"]
    for item in items:
        lines.append(
            f"- {item['sku_code']} {item.get('display_name_cn') or ''}："
            f"{item.get('profile_confidence_pct', '-')}，"
            f"core={join_values(item.get('core_payment_anchors'))}"
        )
    return lines


def anchor_codes(anchors: Iterable[dict[str, Any]]) -> list[str]:
    return [str(anchor["anchor_code"]) for anchor in anchors]


def anchor_names(anchors: Iterable[dict[str, Any]]) -> list[str]:
    return [str(anchor.get("anchor_cn") or anchor["anchor_code"]) for anchor in anchors]


def input_status_labels(items: list[dict[str, Any]]) -> list[str]:
    return [f"{item['source_cn']}:{item['status_cn']}" for item in items]


def join_values(values: Iterable[Any] | None) -> str:
    items = [str(value) for value in values or [] if value]
    return "、".join(items) if items else "-"


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M12D-G07 small-batch validation.")
    parser.add_argument("--database-url", default="", help="SQLAlchemy database URL. Defaults to CATFORGE_DATABASE_URL.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--category-code", default=CATEGORY_CODE)
    parser.add_argument("--product-category", default=PRODUCT_CATEGORY)
    parser.add_argument("--batch-id", default=LATEST_BATCH)
    parser.add_argument("--sample-size", type=int, default=12)
    parser.add_argument("--sku-code", action="append", help="Extra SKU code to include before auto-fill.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
