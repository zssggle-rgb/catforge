#!/usr/bin/env python3
"""Small-batch validation for AC M12D SKU purchase reason profiles."""

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
CATEGORY_CODE = "AC"
PRODUCT_CATEGORY = "ac"
DEFAULT_BATCH_ID = "m00_20260624000202_1150a669"
MARKET_WINDOW = "full_observed_window"
ANALYSIS_POPULATION = "fact_complete_with_comment"
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"
DEFAULT_SAMPLE_SKUS = (
    "AC00038063",
    "AC00028640",
    "AC00029751",
    "AC00036139",
    "AC00038662",
    "AC00028642",
    "AC00036739",
    "AC00036333",
    "AC00035996",
    "AC00036020",
    "AC00038680",
    "AC00034731",
    "AC00039165",
    "AC00038066",
    "AC00034959",
)
MISSING_M12C_SAMPLE_SKUS = {"AC00039165", "AC00038066", "AC00034959"}
NEGATIVE_COMMENT_SAMPLE_SKUS = {"AC00035996", "AC00036020"}
LOW_CONFIDENCE_THRESHOLD = Decimal("0.5000")


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db:
        payload = validate_small_batch(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            product_category=args.product_category,
            batch_id=args.batch_id,
            sample_size=args.sample_size,
            extra_skus=tuple(args.sku_code or ()),
        )

    json_path = output_dir / "M12D_AC_G07_small_batch_validation.json"
    md_path = output_dir / "M12D_AC_G07_small_batch_validation_report.md"
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
        "task": "AC-M12D-G07 small-batch validation",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category.upper(),
        "requested_batch_id": batch_id,
        "resolved_batch_id": resolved_batch_id,
        "sample_size": len(results),
        "sample_selection_note_cn": "固定使用 G01 证据审计确认的 AC 15 个验证样本；不足时才按 M07 市场画像补齐。",
        "source_note_cn": "只读当前 Core3 AC 结果；本脚本只调用 M12D 单 SKU 预览服务，不写入生产表。",
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
        .where(entities.Core3SkuMarketProfile.analysis_window == MARKET_WINDOW)
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
            max_anchors=20,
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
        "supporting_anchor_names": anchor_names(supporting_anchors),
        "weak_expression_anchor_names": anchor_names(weak_anchors),
        "risk_drag_anchor_names": anchor_names(risk_anchors),
        "core_payment_anchor_details": anchor_details(core_anchors),
        "supporting_anchor_details": anchor_details(supporting_anchors),
        "weak_expression_anchor_details": anchor_details(weak_anchors),
        "risk_drag_anchor_details": anchor_details(risk_anchors),
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
    risk_anchors: list[dict[str, Any]],
    input_status: list[dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    if profile_confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append("low_confidence")
    if profile.get("review_required"):
        flags.append("review_required")
    if core_anchors:
        flags.append("has_core_payment_anchor")
    if risk_anchors:
        flags.append("has_risk_drag_anchor")
    if any(item["status"] in {"missing", "unknown", "conflict"} for item in input_status):
        flags.append("input_gap_or_conflict")
    if sku_code in MISSING_M12C_SAMPLE_SKUS:
        if core_anchors:
            flags.append("missing_m12c_misclassified_as_core")
        else:
            flags.append("missing_m12c_correctly_degraded")
    if sku_code in NEGATIVE_COMMENT_SAMPLE_SKUS:
        if risk_anchors:
            flags.append("negative_comment_risk_detected")
        elif core_anchors:
            flags.append("negative_comment_core_review_needed")
        else:
            flags.append("negative_comment_not_core")
    return flags


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    low_confidence = [item for item in results if "low_confidence" in item["validation_flags"]]
    review_required = [item for item in results if "review_required" in item["validation_flags"]]
    core_payment = [item for item in results if item["core_payment_anchors"]]
    risk_drag = [item for item in results if item["risk_drag_anchors"]]
    missing_m12c_failures = [
        item for item in results if "missing_m12c_misclassified_as_core" in item["validation_flags"]
    ]
    missing_m12c_degraded = [
        item for item in results if "missing_m12c_correctly_degraded" in item["validation_flags"]
    ]
    negative_risk_detected = [
        item for item in results if "negative_comment_risk_detected" in item["validation_flags"]
    ]
    negative_core_review = [
        item for item in results if "negative_comment_core_review_needed" in item["validation_flags"]
    ]
    preview_failed = [item for item in results if "preview_failed" in item["validation_flags"]]
    return {
        "total_sku_count": len(results),
        "preview_failed_count": len(preview_failed),
        "low_confidence_count": len(low_confidence),
        "review_required_count": len(review_required),
        "core_payment_present_count": len(core_payment),
        "risk_drag_count": len(risk_drag),
        "missing_m12c_core_misclassification_count": len(missing_m12c_failures),
        "missing_m12c_correctly_degraded_count": len(missing_m12c_degraded),
        "negative_comment_risk_detected_count": len(negative_risk_detected),
        "negative_comment_core_review_needed_count": len(negative_core_review),
        "preview_failed_skus": brief_skus(preview_failed),
        "low_confidence_skus": brief_skus(low_confidence),
        "review_required_skus": brief_skus(review_required),
        "core_payment_skus": brief_skus(core_payment),
        "risk_drag_skus": brief_skus(risk_drag),
        "missing_m12c_guardrail": missing_m12c_guardrail(results),
        "negative_comment_guardrail": negative_comment_guardrail(results),
    }


def build_rule_correction_record(results: list[dict[str, Any]], resolved_batch_id: str) -> list[dict[str, Any]]:
    records = [
        {
            "issue_code": "ac_upstream_version_routing",
            "status": "fixed_in_g07",
            "finding_cn": (
                "G07 验证前发现 ContextBuilder 默认读取 TV 上游 taxonomy/rule version，"
                "真实 AC 数据会被误判为 M04C/M05C/M09C/M10C/M11C 缺失。"
            ),
            "correction_cn": "已按 product_category 自动选择 AC/TV 上游版本，并用 AC fixture 回归测试覆盖。",
            "evidence_cn": f"本轮 resolved_batch_id={resolved_batch_id}；AC 小批量输入覆盖以报告 SKU 明细为准。",
        }
    ]
    missing_m12c_check = missing_m12c_guardrail(results)
    records.append(
        {
            "issue_code": "missing_m12c_core_guardrail",
            "status": missing_m12c_check["status"],
            "finding_cn": missing_m12c_check["message_cn"],
            "correction_cn": "G07 不放宽核心门槛；缺 M12C 样本若进入 core_payment 则阻断进入 G08。",
            "evidence_cn": join_values(item["sku_code"] for item in missing_m12c_check.get("checked_skus", [])),
        }
    )
    negative_comment_check = negative_comment_guardrail(results)
    records.append(
        {
            "issue_code": "negative_comment_risk_guardrail",
            "status": negative_comment_check["status"],
            "finding_cn": negative_comment_check["message_cn"],
            "correction_cn": "G07 不调整负评规则；负评样本若仍有核心理由，后续需在 G08 前人工复核。",
            "evidence_cn": join_values(item["sku_code"] for item in negative_comment_check.get("checked_skus", [])),
        }
    )
    return records


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# AC-M12D-G07 小批量验证与规则修正记录",
        "",
        f"- 生成时间 UTC：{payload['generated_at_utc']}",
        f"- 项目：{payload['project_id']} / {payload['category_code']}",
        f"- 请求批次：{payload['requested_batch_id']}",
        f"- 解析批次：{payload['resolved_batch_id']}",
        f"- 样本数：{payload['sample_size']}",
        f"- 样本口径：{payload['sample_selection_note_cn']}",
        f"- 读取口径：{payload['source_note_cn']}",
        "",
        "## 汇总",
        "",
        f"- 预览失败 SKU：{summary['preview_failed_count']}",
        f"- 低置信 SKU：{summary['low_confidence_count']}",
        f"- 需复核 SKU：{summary['review_required_count']}",
        f"- 有核心成交理由 SKU：{summary['core_payment_present_count']}",
        f"- 有风险拖拽 SKU：{summary['risk_drag_count']}",
        f"- 缺 M12C 样本误判核心：{summary['missing_m12c_core_misclassification_count']}",
        f"- 负评样本仍需复核核心：{summary['negative_comment_core_review_needed_count']}",
        "",
        "## SKU 明细",
        "",
        "| SKU | 产品 | 状态 | 置信度 | 核心成交理由 | 支撑理由 | 弱表达 | 风险 | 非 ready 输入 | 旗标 |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["sample_results"]:
        lines.append(
            "| "
            f"{item['sku_code']} | "
            f"{item.get('display_name_cn') or '-'} | "
            f"{item.get('status_cn') or item.get('status')} | "
            f"{item.get('profile_confidence_pct', '-')} | "
            f"{join_values(item.get('core_payment_anchor_names'))} | "
            f"{join_values(item.get('supporting_anchor_names'))} | "
            f"{join_values(item.get('weak_expression_anchor_names'))} | "
            f"{join_values(item.get('risk_drag_anchor_names'))} | "
            f"{join_values(input_status_labels(item.get('non_ready_inputs') or []))} | "
            f"{join_values(item.get('validation_flags'))} |"
        )

    lines.extend(["", "## 每 SKU 成交理由解释", ""])
    for item in payload["sample_results"]:
        lines.extend(render_sku_reason_details(item))

    lines.extend(["", "## 低置信与复核清单", ""])
    lines.extend(render_brief_list("预览失败 SKU", summary["preview_failed_skus"]))
    lines.extend(render_brief_list("低置信 SKU", summary["low_confidence_skus"]))
    lines.extend(render_brief_list("需复核 SKU", summary["review_required_skus"]))
    lines.extend(render_brief_list("风险拖拽 SKU", summary["risk_drag_skus"]))

    lines.extend(["", "## 缺 M12C 与负评样本门槛", ""])
    for check_key in ("missing_m12c_guardrail", "negative_comment_guardrail"):
        check = summary[check_key]
        lines.append(f"- {check_key}：{check['status']}，{check['message_cn']}")

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


def render_sku_reason_details(item: dict[str, Any]) -> list[str]:
    lines = [f"### {item['sku_code']} {item.get('display_name_cn') or ''}".rstrip()]
    if item.get("message_cn"):
        return [*lines, f"- 预览失败：{item['message_cn']}"]
    sections = (
        ("核心成交理由", item.get("core_payment_anchor_details") or []),
        ("支撑理由", item.get("supporting_anchor_details") or []),
        ("弱表达", item.get("weak_expression_anchor_details") or []),
        ("风险拖拽", item.get("risk_drag_anchor_details") or []),
    )
    has_any = False
    for title, anchors in sections:
        if not anchors:
            continue
        has_any = True
        lines.append(f"- {title}：")
        for anchor in anchors:
            support = anchor.get("support_summary_cn") or "-"
            weakness = anchor.get("weakness_summary_cn") or "-"
            lines.append(
                f"  - {anchor.get('anchor_cn') or anchor.get('anchor_code')}："
                f"{anchor.get('evidence_strength_cn')} / {anchor.get('confidence_pct')}；"
                f"{support}；弱点/风险：{weakness}"
            )
    if not has_any:
        lines.append("- 当前证据未形成可展示的成交理由锚点。")
    return [*lines, ""]


def missing_m12c_guardrail(results: list[dict[str, Any]]) -> dict[str, Any]:
    checked = [item for item in results if item["sku_code"] in MISSING_M12C_SAMPLE_SKUS]
    failures = [item for item in checked if "missing_m12c_misclassified_as_core" in item["validation_flags"]]
    if failures:
        return {
            "status": "failed",
            "message_cn": "缺 M12C 样本仍出现 core_payment，需要先修正规则再进入 G08。",
            "checked_skus": brief_skus(checked),
        }
    if checked:
        return {
            "status": "passed",
            "message_cn": "缺 M12C 样本未进入 core_payment，符合降级要求。",
            "checked_skus": brief_skus(checked),
        }
    return {"status": "not_checked", "message_cn": "样本中未包含缺 M12C SKU。", "checked_skus": []}


def negative_comment_guardrail(results: list[dict[str, Any]]) -> dict[str, Any]:
    checked = [item for item in results if item["sku_code"] in NEGATIVE_COMMENT_SAMPLE_SKUS]
    core_review = [item for item in checked if "negative_comment_core_review_needed" in item["validation_flags"]]
    risk_detected = [item for item in checked if "negative_comment_risk_detected" in item["validation_flags"]]
    if core_review:
        return {
            "status": "review_required",
            "message_cn": "部分负评样本仍出现 core_payment，需结合评论明细人工复核。",
            "checked_skus": brief_skus(checked),
        }
    if risk_detected:
        return {
            "status": "passed",
            "message_cn": "负评样本已识别为风险拖拽。",
            "checked_skus": brief_skus(checked),
        }
    if checked:
        return {
            "status": "passed_no_core",
            "message_cn": "负评样本未形成 core_payment，但也未显式进入风险拖拽。",
            "checked_skus": brief_skus(checked),
        }
    return {"status": "not_checked", "message_cn": "样本中未包含负评 SKU。", "checked_skus": []}


def brief_skus(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sku_code": item["sku_code"],
            "display_name_cn": item.get("display_name_cn"),
            "status": item.get("status"),
            "profile_confidence_pct": item.get("profile_confidence_pct"),
            "core_payment_anchors": item.get("core_payment_anchors") or [],
            "risk_drag_anchors": item.get("risk_drag_anchors") or [],
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
            f"core={join_values(item.get('core_payment_anchors'))}，"
            f"risk={join_values(item.get('risk_drag_anchors'))}"
        )
    return lines


def anchor_codes(anchors: Iterable[dict[str, Any]]) -> list[str]:
    return [str(anchor["anchor_code"]) for anchor in anchors]


def anchor_names(anchors: Iterable[dict[str, Any]]) -> list[str]:
    return [str(anchor.get("anchor_cn") or anchor["anchor_code"]) for anchor in anchors]


def anchor_details(anchors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "anchor_code": anchor.get("anchor_code"),
            "anchor_cn": anchor.get("anchor_cn"),
            "evidence_strength": anchor.get("evidence_strength"),
            "evidence_strength_cn": anchor.get("evidence_strength_cn"),
            "confidence_pct": anchor.get("confidence_pct"),
            "evidence_domains_cn": anchor.get("evidence_domains_cn") or [],
            "support_summary_cn": anchor.get("support_summary_cn"),
            "weakness_summary_cn": anchor.get("weakness_summary_cn"),
            "risk_flags": anchor.get("risk_flags") or [],
            "downgrade_reason_code": anchor.get("downgrade_reason_code"),
        }
        for anchor in anchors
    ]


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
    parser = argparse.ArgumentParser(description="Run AC-M12D-G07 small-batch validation.")
    parser.add_argument("--database-url", default="", help="SQLAlchemy database URL. Defaults to CATFORGE_DATABASE_URL.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--category-code", default=CATEGORY_CODE)
    parser.add_argument("--product-category", default=PRODUCT_CATEGORY)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--sample-size", type=int, default=len(DEFAULT_SAMPLE_SKUS))
    parser.add_argument("--sku-code", action="append", help="Extra SKU code to include before auto-fill.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
