#!/usr/bin/env python3
"""Generate draft AC M12D purchase reason profiles for the full AC batch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models import entities  # noqa: E402
from app.services.core3_real_data.analyst.analyst_repository import batch_ids_from_scope  # noqa: E402
from app.services.core3_real_data.analyst.analyst_service import (  # noqa: E402
    LATEST_BATCH,
    CatForgeAnalystService,
)
from app.services.core3_real_data.constants import (  # noqa: E402
    CORE3_M07_RULE_VERSION,
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_AC_PROFILE_VERSION,
    CORE3_M12D_RULE_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.purchase_reason_profile_runner import (  # noqa: E402
    PurchaseReasonProfileBatchGenerator,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext  # noqa: E402


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CODE = "AC"
PRODUCT_CATEGORY = "ac"
DEFAULT_BATCH_ID = "m00_20260624000202_1150a669"
MARKET_WINDOW = "full_observed_window"
ANALYSIS_POPULATION = "fact_complete_with_comment"
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"
DEFAULT_PROFILE_VERSION = CORE3_M12D_AC_PROFILE_VERSION


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required.")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db:
        payload = generate_full_ac_batch(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            product_category=args.product_category,
            requested_batch_id=args.batch_id,
            m12d_profile_version=args.profile_version,
            storage_batch_id=args.storage_batch_id,
            write=args.write,
            limit=args.limit,
            detail_limit=args.detail_limit,
        )
        if args.write:
            db.commit()
        else:
            db.rollback()

    json_path = output_dir / "M12D_AC_G08_full_batch_generation.json"
    md_path = output_dir / "M12D_AC_G08_full_batch_generation_report.md"
    payload["artifacts"] = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    md_path.write_text(render_markdown_report(payload), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


def generate_full_ac_batch(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    product_category: str,
    requested_batch_id: str,
    m12d_profile_version: str,
    storage_batch_id: str,
    write: bool,
    limit: int,
    detail_limit: int,
) -> dict[str, Any]:
    resolved_batch_id = resolve_batch_id(
        db,
        project_id=project_id,
        category_code=category_code,
        product_category=product_category,
        batch_id=requested_batch_id,
    )
    source_batch_ids = batch_ids_from_scope(resolved_batch_id)
    normalized_storage_batch_id = storage_batch_id.strip() or (source_batch_ids[0] if source_batch_ids else resolved_batch_id)
    sku_codes = select_full_ac_skus(
        db,
        project_id=project_id,
        category_code=category_code,
        product_category=product_category,
        batch_id=resolved_batch_id,
        limit=limit,
    )
    repository_context = Core3RepositoryContext(
        db=db,
        project_id=project_id,
        category_code=Core3CategoryCode(category_code),
    )
    result = PurchaseReasonProfileBatchGenerator(repository_context).generate(
        batch_id=resolved_batch_id,
        storage_batch_id=normalized_storage_batch_id,
        sku_codes=sku_codes,
        product_category=product_category,
        taxonomy_version=CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        m12d_profile_version=m12d_profile_version,
        write=write,
        generated_by="scripts/m12d_ac_g08_generate_full_batch.py",
        detail_limit=detail_limit,
    )
    db_written_counts = written_record_counts(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=normalized_storage_batch_id,
        m12d_profile_version=m12d_profile_version,
    ) if write else {}
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": "AC-M12D-G08 full AC batch generation",
        "project_id": project_id,
        "category_code": category_code,
        "product_category": product_category.upper(),
        "requested_batch_id": requested_batch_id,
        "resolved_batch_id": resolved_batch_id,
        "storage_batch_id": normalized_storage_batch_id,
        "source_batch_ids": list(source_batch_ids),
        "m12d_profile_version": m12d_profile_version,
        "taxonomy_version": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        "rule_version": CORE3_M12D_RULE_VERSION,
        "write_mode": "write" if write else "dry_run",
        "selected_sku_count": len(sku_codes),
        "status": enum_value(result.status),
        "warnings": result.warnings,
        "summary": result.summary,
        "db_written_counts": db_written_counts,
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


def select_full_ac_skus(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    product_category: str,
    batch_id: str,
    limit: int,
) -> list[str]:
    sku_prefix = product_category.strip().upper()
    batch_ids = batch_ids_from_scope(batch_id)
    if not batch_ids:
        return []
    stmt = (
        select(entities.Core3SkuMarketProfile.sku_code)
        .distinct()
        .where(entities.Core3SkuMarketProfile.project_id == project_id)
        .where(entities.Core3SkuMarketProfile.category_code == category_code)
        .where(entities.Core3SkuMarketProfile.batch_id.in_(batch_ids))
        .where(entities.Core3SkuMarketProfile.sku_code.like(f"{sku_prefix}%"))
        .where(entities.Core3SkuMarketProfile.analysis_window == MARKET_WINDOW)
        .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
        .where(entities.Core3SkuMarketProfile.is_current.is_(True))
        .order_by(entities.Core3SkuMarketProfile.sku_code)
    )
    if limit > 0:
        stmt = stmt.limit(limit)
    return [str(sku_code) for sku_code in db.execute(stmt).scalars()]


def written_record_counts(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    m12d_profile_version: str,
) -> dict[str, int]:
    filters = {
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "m12d_profile_version": m12d_profile_version,
        "rule_version": CORE3_M12D_RULE_VERSION,
    }
    counts: dict[str, int] = {}
    for key, model_cls in (
        ("version_count", entities.Core3PurchaseReasonProfileVersion),
        ("profile_count", entities.Core3SkuPurchaseReasonProfile),
        ("anchor_count", entities.Core3SkuPurchaseReasonAnchor),
    ):
        stmt = select(func.count()).select_from(model_cls)
        for field_name, value in filters.items():
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        counts[key] = int(db.execute(stmt).scalar_one())
    return counts


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# AC-M12D-G08 全量 AC batch 生成报告",
        "",
        f"- 生成时间 UTC：{payload['generated_at_utc']}",
        f"- 项目：{payload['project_id']} / {payload['category_code']}",
        f"- 请求批次：{payload['requested_batch_id']}",
        f"- 读取批次：{payload['resolved_batch_id']}",
        f"- 入库批次：{payload['storage_batch_id']}",
        f"- 版本：{payload['m12d_profile_version']}",
        f"- taxonomy：{payload['taxonomy_version']}",
        f"- 写入模式：{payload['write_mode']}",
        f"- SKU 数：{payload['selected_sku_count']}",
        f"- 状态：{payload['status']}",
        "",
        "## 质量统计",
        "",
        f"- 成功率：{summary['success_rate']}",
        f"- 低置信率：{summary['low_confidence_rate']}（{summary['low_confidence_count']}）",
        f"- 核心成交理由缺失率：{summary['core_payment_missing_rate']}（{summary['core_payment_missing_count']}）",
        f"- 需复核率：{summary['review_required_rate']}（{summary['review_required_count']}）",
        f"- 失败数：{summary['failed_count']}",
        f"- Profile 记录数：{summary['profile_record_count']}",
        f"- Anchor 记录数：{summary['anchor_record_count']}",
    ]
    if payload.get("db_written_counts"):
        counts = payload["db_written_counts"]
        lines.extend(
            [
                "",
                "## 入库校验",
                "",
                f"- Version 记录：{counts.get('version_count', 0)}",
                f"- Profile 记录：{counts.get('profile_count', 0)}",
                f"- Anchor 记录：{counts.get('anchor_count', 0)}",
            ]
        )

    lines.extend(["", "## 锚点分布", ""])
    role_counts = summary.get("role_counts") or {}
    if role_counts:
        for role, count in sorted(role_counts.items()):
            lines.append(f"- {role}: {count}")
    else:
        lines.append("- 无")

    lines.extend(["", "### Top 购买理由", ""])
    top_anchor_codes = summary.get("top_anchor_codes") or []
    if top_anchor_codes:
        for item in top_anchor_codes:
            lines.append(f"- {item['code']}: {item['count']}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 失败清单", ""])
    lines.extend(render_failure_list(summary.get("failed_skus") or []))
    lines.extend(["", "## 低置信清单（前 30）", ""])
    lines.extend(render_profile_list(summary.get("low_confidence_skus") or []))
    lines.extend(["", "## 需复核清单（前 30）", ""])
    lines.extend(render_profile_list(summary.get("review_required_skus") or []))
    lines.extend(["", "## 核心成交理由缺失清单（前 30）", ""])
    lines.extend(render_profile_list(summary.get("core_payment_missing_skus") or []))
    lines.extend(
        [
            "",
            "## 后续任务",
            "",
            "- AC-M12D-G09：在本草稿版本基础上执行发布版本与下游契约冻结。",
            "- G09 前竞品智能体不得直接消费本草稿版本作为正式结论。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_profile_list(items: list[dict[str, Any]], *, limit: int = 30) -> list[str]:
    if not items:
        return ["- 无"]
    lines = []
    for item in items[:limit]:
        reasons = ",".join(item.get("review_reasons") or [])
        lines.append(
            f"- {item['sku_code']} {item.get('display_name_cn') or ''}："
            f"status={item.get('status')}，confidence={item.get('profile_confidence')}，"
            f"core={join_values(item.get('core_payment_anchors'))}"
            f"{f'，reasons={reasons}' if reasons else ''}"
        )
    return lines


def render_failure_list(items: list[dict[str, Any]], *, limit: int = 50) -> list[str]:
    if not items:
        return ["- 无"]
    return [f"- {item.get('sku_code')}: {item.get('message')}" for item in items[:limit]]


def join_values(values: Iterable[Any] | None) -> str:
    items = [str(value) for value in values or [] if value]
    return "、".join(items) if items else "-"


def enum_value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate draft AC M12D profiles for the full AC batch.")
    parser.add_argument("--database-url", default="", help="SQLAlchemy database URL. Defaults to CATFORGE_DATABASE_URL.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--category-code", default=CATEGORY_CODE)
    parser.add_argument("--product-category", default=PRODUCT_CATEGORY)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--profile-version", default=DEFAULT_PROFILE_VERSION)
    parser.add_argument("--storage-batch-id", default="")
    parser.add_argument("--limit", type=int, default=0, help="Optional SKU limit for smoke runs. 0 means full batch.")
    parser.add_argument("--detail-limit", type=int, default=50)
    parser.add_argument("--write", action="store_true", help="Write draft records. Omit for dry-run.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
