#!/usr/bin/env python3
"""Publish a generated M12D version and export downstream contract fixtures."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models import entities  # noqa: E402
from app.services.core3_real_data.constants import (  # noqa: E402
    CORE3_M12D_RULE_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.purchase_reason_profile_contract import (  # noqa: E402
    get_downstream_read_contract,
)
from app.services.core3_real_data.purchase_reason_profile_repositories import (  # noqa: E402
    PurchaseReasonProfileRepository,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext  # noqa: E402


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CODE = "TV"
BATCH_ID = "m00_20260623014631_c8630747"
PROFILE_VERSION = "m12d_tv_purchase_reason_profile_v0_1_draft"
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"
DEFAULT_SAMPLE_SKUS = (
    "TV00029112",  # 海信 65E7Q
    "TV00029936",  # 创维 65A7H PRO
    "TV00027801",  # TCL 65Q9L PRO
    "TV00029020",  # 小米 L65MC-SP
    "TV00028829",  # 创维 65A6F ULTRA
)


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
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        payload = publish_and_export_contract(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
            m12d_profile_version=args.profile_version,
            sample_skus=tuple(args.sku_code or DEFAULT_SAMPLE_SKUS),
            publish=args.publish,
            published_by=args.published_by,
            release_note_cn=args.release_note_cn,
        )
        if args.publish:
            db.commit()
        else:
            db.rollback()

    json_path = output_dir / "M12D_G09_published_contract_fixture.json"
    md_path = output_dir / "M12D_G09_published_contract_report.md"
    payload["artifacts"] = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    md_path.write_text(render_markdown_report(payload), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


def publish_and_export_contract(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    m12d_profile_version: str,
    sample_skus: tuple[str, ...],
    publish: bool,
    published_by: str,
    release_note_cn: str,
    task_label: str = "M12D-G09 publish version and freeze downstream contract",
    missing_sku_code: str = "TV_M12D_NOT_FOUND",
    unpublished_sku_code: str | None = None,
) -> dict[str, Any]:
    repository = PurchaseReasonProfileRepository(
        Core3RepositoryContext(
            db=db,
            project_id=project_id,
            category_code=Core3CategoryCode(category_code),
        )
    )
    published_version = None
    if publish:
        published_version = repository.publish_version(
            batch_id=batch_id,
            m12d_profile_version=m12d_profile_version,
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by=published_by,
            release_note_cn=release_note_cn,
        )
    else:
        published_version = repository._find_published_version(  # noqa: SLF001 - script-level readback for fixture export.
            batch_id=batch_id,
            m12d_profile_version=m12d_profile_version,
        )

    contracts = [
        get_downstream_read_contract(
            repository,
            batch_id=batch_id,
            sku_code=sku_code.strip().upper(),
            m12d_profile_version=m12d_profile_version,
        )
        for sku_code in sample_skus
    ]
    missing_contract = get_downstream_read_contract(
        repository,
        batch_id=batch_id,
        sku_code=missing_sku_code,
        m12d_profile_version=m12d_profile_version,
    )
    unpublished_version_contract = get_downstream_read_contract(
        repository,
        batch_id=batch_id,
        sku_code=unpublished_sku_code or (sample_skus[0].strip().upper() if sample_skus else "TV00029112"),
        m12d_profile_version=f"{m12d_profile_version}_unpublished_fixture",
    )
    summary = published_contract_summary(db, project_id=project_id, category_code=category_code, batch_id=batch_id, version=m12d_profile_version)
    consumption_state_counts: dict[str, int] = {}
    for contract in contracts:
        consumption_state_counts[contract.consumption_state] = consumption_state_counts.get(contract.consumption_state, 0) + 1

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": task_label,
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "m12d_profile_version": m12d_profile_version,
        "rule_version": CORE3_M12D_RULE_VERSION,
        "publish_mode": "publish" if publish else "export_only",
        "published_version": version_payload(published_version),
        "summary": {
            **summary,
            "sample_contract_count": len(contracts),
            "sample_consumption_state_counts": consumption_state_counts,
        },
        "downstream_contract": {
            "lookup_key": "category_code + project_id + batch_id + m12d_profile_version + sku_code",
            "required_contract_fields": [
                "consumption_state",
                "release_quality_status",
                "version_quality_notes",
                "capabilities",
            ],
            "states": {
                "published_ready": "已发布且该 SKU 可正常进入购买理由强比较。",
                "published_degraded": "已发布且事实维度仍可消费；购买理由比较按 SKU 能力限制执行。",
                "published_unusable": "已发布但画像失败或关键输入缺失；目标阻断强排序，候选退出强替代判断。",
                "not_found": "未发布或不存在；下游不得临时生成或补写成交理由。",
            },
            "required_profile_fields": [
                "status",
                "core_reasons_cn",
                "core_payment_anchors",
                "supporting_anchors",
                "weak_expression_anchors",
                "risk_drag_anchors",
                "anchors",
                "profile_confidence",
                "degradation_reasons",
            ],
        },
        "sample_contracts": [contract.model_dump(mode="json") for contract in contracts],
        "missing_contract_fixture": missing_contract.model_dump(mode="json"),
        "unpublished_version_contract_fixture": unpublished_version_contract.model_dump(mode="json"),
    }


def published_contract_summary(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    version: str,
) -> dict[str, Any]:
    profile_filters = (
        entities.Core3SkuPurchaseReasonProfile.project_id == project_id,
        entities.Core3SkuPurchaseReasonProfile.category_code == category_code,
        entities.Core3SkuPurchaseReasonProfile.batch_id == batch_id,
        entities.Core3SkuPurchaseReasonProfile.m12d_profile_version == version,
        entities.Core3SkuPurchaseReasonProfile.rule_version == CORE3_M12D_RULE_VERSION,
    )
    anchor_filters = (
        entities.Core3SkuPurchaseReasonAnchor.project_id == project_id,
        entities.Core3SkuPurchaseReasonAnchor.category_code == category_code,
        entities.Core3SkuPurchaseReasonAnchor.batch_id == batch_id,
        entities.Core3SkuPurchaseReasonAnchor.m12d_profile_version == version,
        entities.Core3SkuPurchaseReasonAnchor.rule_version == CORE3_M12D_RULE_VERSION,
    )
    version_row = db.execute(
        select(entities.Core3PurchaseReasonProfileVersion).where(
            entities.Core3PurchaseReasonProfileVersion.project_id == project_id,
            entities.Core3PurchaseReasonProfileVersion.category_code == category_code,
            entities.Core3PurchaseReasonProfileVersion.batch_id == batch_id,
            entities.Core3PurchaseReasonProfileVersion.m12d_profile_version == version,
            entities.Core3PurchaseReasonProfileVersion.rule_version == CORE3_M12D_RULE_VERSION,
        )
    ).scalars().first()
    return {
        "version_rows": 1 if version_row else 0,
        "version_release_status": getattr(version_row, "release_status", None),
        "version_is_current": getattr(version_row, "is_current", None),
        "profile_rows": db.execute(select(func.count()).select_from(entities.Core3SkuPurchaseReasonProfile).where(*profile_filters)).scalar_one(),
        "published_profile_rows": db.execute(
            select(func.count()).select_from(entities.Core3SkuPurchaseReasonProfile).where(
                *profile_filters,
                entities.Core3SkuPurchaseReasonProfile.release_status == "published",
                entities.Core3SkuPurchaseReasonProfile.is_current.is_(True),
            )
        ).scalar_one(),
        "anchor_rows": db.execute(select(func.count()).select_from(entities.Core3SkuPurchaseReasonAnchor).where(*anchor_filters)).scalar_one(),
        "published_anchor_rows": db.execute(
            select(func.count()).select_from(entities.Core3SkuPurchaseReasonAnchor).where(
                *anchor_filters,
                entities.Core3SkuPurchaseReasonAnchor.release_status == "published",
                entities.Core3SkuPurchaseReasonAnchor.is_current.is_(True),
            )
        ).scalar_one(),
    }


def version_payload(version: Any | None) -> dict[str, Any] | None:
    if version is None:
        return None
    return {
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "batch_id": version.batch_id,
        "m12d_profile_version": version.m12d_profile_version,
        "release_status": version.release_status,
        "release_quality_status": version.release_quality_status,
        "is_current": version.is_current,
        "published_at": version.published_at,
        "published_by": version.published_by,
        "release_note_cn": version.release_note_cn,
        "sku_count": version.sku_count,
        "ready_count": version.ready_count,
        "review_required_count": version.review_required_count,
        "missing_input_count": version.missing_input_count,
        "failed_count": version.failed_count,
        "low_confidence_count": version.low_confidence_count,
        "core_payment_missing_count": version.core_payment_missing_count,
    }


def render_markdown_report(
    payload: dict[str, Any],
    *,
    title: str = "# M12D-G09 发布版本与下游契约冻结报告",
    next_step_lines: tuple[str, ...] | None = None,
) -> str:
    summary = payload["summary"]
    lines = [
        title,
        "",
        f"- 生成时间 UTC：{payload['generated_at_utc']}",
        f"- 项目：{payload['project_id']} / {payload['category_code']}",
        f"- 批次：{payload['batch_id']}",
        f"- 版本：{payload['m12d_profile_version']}",
        f"- 发布模式：{payload['publish_mode']}",
        f"- 版本状态：{summary.get('version_release_status')} / current={summary.get('version_is_current')}",
        f"- Profile：{summary.get('published_profile_rows')}/{summary.get('profile_rows')} 已发布 current",
        f"- Anchor：{summary.get('published_anchor_rows')}/{summary.get('anchor_rows')} 已发布 current",
        "",
    ]
    quality_gate = payload.get("quality_gate")
    if quality_gate:
        lines.extend(
            [
                "## 发布质量口径",
                "",
                f"- 发布决策：{quality_gate.get('publish_decision')}",
                f"- 发布说明：{quality_gate.get('release_semantics_cn')}",
                f"- 需复核 SKU：{quality_gate.get('review_required_count')}",
                f"- 低置信 SKU：{quality_gate.get('low_confidence_count')}",
                f"- 核心成交理由缺失 SKU：{quality_gate.get('core_payment_missing_count')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 下游读取契约",
            "",
            "- 读取键：`category_code + project_id + batch_id + m12d_profile_version + sku_code`",
            "- 目标 SKU `not_found` 或 `published_unusable`：阻断强排序，不临时生成成交理由。",
            "- 候选 SKU `not_found` 或 `published_unusable`：退出强替代判断或退出 Top 3。",
            "- `published_degraded`：可降级消费，但必须展示置信度和降级原因。",
            "- 下游不得修改 M12D 原始锚点角色。",
            "",
            "## Fixture 样本",
            "",
            "| SKU | 产品 | 状态 | 下游动作 | 置信度 | 核心锚点 | 降级原因 |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for contract in payload["sample_contracts"]:
        profile = contract.get("profile") or {}
        lines.append(
            "| "
            f"{(profile.get('sku_code') or contract['lookup_key'].get('sku_code'))} | "
            f"{profile.get('display_name_cn') or '-'} | "
            f"{contract.get('consumption_state')} | "
            f"{contract.get('downstream_action')} | "
            f"{profile.get('profile_confidence') or '-'} | "
            f"{join_values(profile.get('core_payment_anchors'))} | "
            f"{join_values(profile.get('degradation_reasons'))} |"
        )
    lines.extend(
        [
            "",
            "## 缺失/未发布 Fixture",
            "",
            f"- 缺失 SKU：{payload['missing_contract_fixture']['consumption_state']} / {payload['missing_contract_fixture']['downstream_action']}",
            f"- 未发布版本：{payload['unpublished_version_contract_fixture']['consumption_state']} / {payload['unpublished_version_contract_fixture']['downstream_action']}",
            "",
            "## 下一步",
            "",
            *(next_step_lines or (
                "- CA-G01 可以基于本 fixture 实现竞品智能体侧 M12D reader。",
                "- CA-G01 不得在竞品智能体中生成或修正 M12D。",
            )),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def join_values(values: Any) -> str:
    if not values:
        return "-"
    return "、".join(str(value) for value in values)


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish M12D version and export downstream contract fixtures.")
    parser.add_argument("--database-url", default="", help="SQLAlchemy database URL. Defaults to CATFORGE_DATABASE_URL.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--category-code", default=CATEGORY_CODE)
    parser.add_argument("--batch-id", default=BATCH_ID)
    parser.add_argument("--profile-version", default=PROFILE_VERSION)
    parser.add_argument("--sku-code", action="append", help="Sample SKU code for fixture export.")
    parser.add_argument("--publish", action="store_true", help="Publish the version before exporting fixtures.")
    parser.add_argument("--published-by", default="codex-m12d-g09")
    parser.add_argument(
        "--release-note-cn",
        default="M12D-G09 发布：基于 G08 TV 全量草稿，冻结下游读取契约和降级语义。",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
