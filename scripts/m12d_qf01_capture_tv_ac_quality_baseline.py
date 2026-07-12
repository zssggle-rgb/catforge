#!/usr/bin/env python3
"""Capture the current read-only TV/AC M12D quality baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

try:  # noqa: E402
    from app.services.core3_real_data.purchase_reason_quality_baseline import capture_quality_baseline  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - supports read-only execution from /tmp on 205
    from purchase_reason_quality_baseline import capture_quality_baseline  # noqa: E402


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db:
        baseline = capture_quality_baseline(
            db,
            project_id=args.project_id,
            categories=tuple(value.strip().upper() for value in args.categories.split(",") if value.strip()),
        )
        db.rollback()

    payload = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), **baseline}
    json_path = output_dir / "M12D_QF01_tv_ac_quality_baseline.json"
    markdown_path = output_dir / "M12D_QF01_tv_ac_quality_baseline_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"json_path": str(json_path), "markdown_path": str(markdown_path), **baseline}, ensure_ascii=False))


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M12D-QF-01 TV/AC 质量基线",
        "",
        f"- 采集时间 UTC：{payload['captured_at_utc']}",
        f"- 项目：`{payload['project_id']}`",
        f"- 基线指纹：`{payload['baseline_fingerprint']}`",
        "- 执行方式：只读；未修改 current/published 数据。",
        "",
    ]
    for category_code, category in payload["categories"].items():
        lines.extend([f"## {category_code}", "", f"- 版本选择：`{category['selection']}`"])
        m12d = category.get("m12d")
        if not m12d:
            lines.extend(["- M12D：未找到可作为基线的版本。", ""])
            continue
        version = m12d["version"]
        lines.extend(
            [
                f"- M12D 版本：`{version['m12d_profile_version']}` / `{version['batch_id']}`",
                f"- 发布状态：`{version['release_status']}` / 质量状态 `{version['release_quality_status']}`",
                f"- 画像/锚点：{m12d['profile_count']} / {m12d['anchor_count']}",
                f"- 状态：{_inline_counts(m12d['status_counts'])}",
                f"- 需复核：{m12d['review_required_count']}",
                f"- 缺少核心锚点：{m12d['core_payment_missing_count']}",
                "",
                "| 上游模块 | SKU 数 | 行数 | 需复核 SKU | 冲突 SKU |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for module_code, summary in category["upstream"].items():
            lines.append(
                f"| {module_code} | {summary['sku_count']} | {summary['row_count']} | "
                f"{summary['review_required_sku_count']} | {summary.get('conflict_sku_count', 0)} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _inline_counts(values: dict[str, Any]) -> str:
    return "、".join(f"`{key}`={value}" for key, value in sorted(values.items())) or "无"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default="")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--categories", default="TV,AC")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    main()
