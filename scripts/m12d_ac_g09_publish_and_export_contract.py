#!/usr/bin/env python3
"""Publish the AC M12D draft version and export downstream contract fixtures."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
SCRIPT_ROOT = REPO_ROOT / "scripts"
for path in (API_ROOT, SCRIPT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.models import entities  # noqa: E402
from app.services.core3_real_data.constants import (  # noqa: E402
    CORE3_M12D_AC_PROFILE_VERSION,
    CORE3_M12D_RULE_VERSION,
)
from m12d_g09_publish_and_export_contract import (  # noqa: E402
    json_default,
    publish_and_export_contract,
    render_markdown_report,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CODE = "AC"
BATCH_ID = "m00_20260624000202_1150a669"
PROFILE_VERSION = CORE3_M12D_AC_PROFILE_VERSION
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"
DEFAULT_SAMPLE_SKUS = (
    "AC00038063",
    "AC00028640",
    "AC00029751",
    "AC00036139",
    "AC00038662",
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
        sample_skus = tuple(args.sku_code) if args.sku_code else select_default_sample_skus(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
            m12d_profile_version=args.profile_version,
        )
        payload = publish_and_export_contract(
            db,
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
            m12d_profile_version=args.profile_version,
            sample_skus=sample_skus,
            publish=args.publish,
            published_by=args.published_by,
            release_note_cn=args.release_note_cn,
            task_label="AC-M12D-G09 publish AC version and freeze downstream contract",
            missing_sku_code="AC_M12D_NOT_FOUND",
            unpublished_sku_code=sample_skus[0] if sample_skus else "AC00038063",
        )
        payload["sample_selection"] = {
            "mode": "explicit" if args.sku_code else "auto_from_ac_draft_profiles",
            "sku_codes": list(sample_skus),
        }
        payload["quality_gate"] = build_quality_gate(payload)
        if args.publish:
            db.commit()
        else:
            db.rollback()

    json_path = output_dir / "M12D_AC_G09_published_contract_fixture.json"
    md_path = output_dir / "M12D_AC_G09_published_contract_report.md"
    payload["artifacts"] = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    md_path.write_text(
        render_markdown_report(
            payload,
            title="# AC-M12D-G09 发布版本与下游契约冻结报告",
            next_step_lines=(
                "- AC-CA-G01 可以基于本 fixture 验收竞品智能体读取 AC M12D。",
                "- AC-CA-G01 不得在竞品智能体中生成或修正 AC M12D。",
            ),
        ),
        encoding="utf-8",
    )
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


def select_default_sample_skus(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    m12d_profile_version: str,
) -> tuple[str, ...]:
    rows = list(
        db.execute(
            select(entities.Core3SkuPurchaseReasonProfile)
            .where(entities.Core3SkuPurchaseReasonProfile.project_id == project_id)
            .where(entities.Core3SkuPurchaseReasonProfile.category_code == category_code)
            .where(entities.Core3SkuPurchaseReasonProfile.batch_id == batch_id)
            .where(entities.Core3SkuPurchaseReasonProfile.m12d_profile_version == m12d_profile_version)
            .where(entities.Core3SkuPurchaseReasonProfile.rule_version == CORE3_M12D_RULE_VERSION)
            .order_by(entities.Core3SkuPurchaseReasonProfile.sku_code)
        ).scalars()
    )
    if not rows:
        return DEFAULT_SAMPLE_SKUS

    with_core = [row.sku_code for row in rows if list(row.core_payment_anchors_json or [])]
    degraded_without_core = [
        row.sku_code
        for row in rows
        if not list(row.core_payment_anchors_json or []) and float(row.profile_confidence or 0) < 0.5
    ]
    with_risk = [row.sku_code for row in rows if list(row.risk_drag_anchors_json or [])]
    selected = _dedupe([*with_core[:2], *degraded_without_core[:2], *with_risk[:1]])
    return tuple(selected[:5] or DEFAULT_SAMPLE_SKUS)


def build_quality_gate(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get("published_version") or {}
    return {
        "publish_decision": "publish_current_with_degraded_consumption_contract"
        if payload.get("publish_mode") == "publish"
        else "export_contract_only",
        "release_semantics_cn": (
            "发布为 current 仅表示下游可以读取冻结契约；低置信、需复核或缺核心理由的 SKU "
            "必须以 published_degraded 降级消费，不得作为无条件强替代结论。"
        ),
        "sku_count": version.get("sku_count"),
        "ready_count": version.get("ready_count"),
        "review_required_count": version.get("review_required_count"),
        "missing_input_count": version.get("missing_input_count"),
        "failed_count": version.get("failed_count"),
        "low_confidence_count": version.get("low_confidence_count"),
        "core_payment_missing_count": version.get("core_payment_missing_count"),
    }


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish AC M12D version and export downstream contract fixtures.")
    parser.add_argument("--database-url", default="", help="SQLAlchemy database URL. Defaults to CATFORGE_DATABASE_URL.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--category-code", default=CATEGORY_CODE)
    parser.add_argument("--batch-id", default=BATCH_ID)
    parser.add_argument("--profile-version", default=PROFILE_VERSION)
    parser.add_argument("--sku-code", action="append", help="Sample SKU code for fixture export.")
    parser.add_argument("--publish", action="store_true", help="Publish the version before exporting fixtures.")
    parser.add_argument("--published-by", default="codex-ac-m12d-g09")
    parser.add_argument(
        "--release-note-cn",
        default="AC M12D v0.2 发布：基于新匹数价格池全量重算，冻结下游读取契约和降级语义。",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
