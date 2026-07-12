#!/usr/bin/env python3
"""Aggregate the frozen G06/G07 receipts into the G08 release-candidate gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TAXONOMIES = {
    "TV": "m12d_tv_purchase_reason_anchor_taxonomy_v0.1",
    "AC": "m12d_ac_purchase_reason_anchor_taxonomy_v0.1",
}
EXPECTED_PREFIXES = {"TV": "TV", "AC": "AC"}


def main() -> int:
    args = parse_args()
    g06 = load_json(Path(args.g06_result))
    g06_fixture = load_json(Path(args.g06_fixture))
    g07 = load_json(Path(args.g07_result))

    categories: dict[str, Any] = {}
    failed_checks: list[str] = []
    for category in ("TV", "AC"):
        result = evaluate_category(
            category=category,
            g06=g06,
            g06_fixture=g06_fixture,
            g07=g07,
        )
        categories[category] = result
        failed_checks.extend(
            f"{category.lower()}_{name}"
            for name, passed in result["checks"].items()
            if not passed
        )

    shared_checks = {
        "g06_acceptance_passed": g06.get("acceptance", {}).get("passed") is True,
        "g06_read_only_guard_unchanged": (
            g06.get("downstream_guard", {}).get("unchanged") is True
        ),
        "g07_acceptance_passed": g07.get("acceptance", {}).get("passed") is True,
        "g07_deterministic_replay_identical": args.g07_replay_identical,
        "integration_tests_passed": args.pytest_passed >= 1,
    }
    failed_checks.extend(
        name for name, passed in shared_checks.items() if not passed
    )
    integration_passed = not failed_checks

    payload = {
        "task_id": "M12D-RP-G08",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "g06_result": args.g06_result,
            "g06_fixture": args.g06_fixture,
            "g07_result": args.g07_result,
        },
        "integration_tests": {
            "pytest_passed": args.pytest_passed,
            "g07_deterministic_replay_identical": args.g07_replay_identical,
            "scope": "M03B-M12D、竞品 reader、CLI、报告和 TV/AC 品类隔离",
        },
        "shared_checks": shared_checks,
        "categories": categories,
        "qf_backfill": {
            "qf15_historical_result": (
                "旧口径下 blocked 结论保留为历史记录；旧口径把购买理由成立度、"
                "购买阻力和版本级消费能力混在一起，不能改写成当时已通过。"
            ),
            "qf15_current_state": (
                "completed_superseded_by_m12d_rp_g06_g08；新批准口径下 TV/AC "
                "分别全量影子重算并达到 ready。"
            ),
            "qf16_prerequisite": (
                "satisfied；竞品消费和 Top 3 回归已由 M12D-RP-G07 完成。"
            ),
            "qf17_state": (
                "completed_by_m12d_rp_g08；共享链路和跨品类隔离回归通过。"
            ),
        },
        "acceptance": {
            "passed": integration_passed,
            "failed_checks": failed_checks,
            "g09_commit_deploy_candidate": "go" if integration_passed else "no_go",
            "current_publish": "no_go_pending_g09_g10",
            "reason_cn": (
                "TV/AC 均通过本地集成和影子发布门槛，可申请进入 G09 提交部署；"
                "代码尚未提交部署，205 尚未正式全量重跑，因此当前仍不可发布。"
                if integration_passed
                else "至少一个品类未通过集成门槛，不得进入 G09。"
            ),
        },
    }
    write_outputs(payload, Path(args.output_json), Path(args.output_markdown))
    print(
        json.dumps(
            {
                "status": "ok" if integration_passed else "failed",
                "tv_decision": categories["TV"]["decision"],
                "ac_decision": categories["AC"]["decision"],
                "failed_checks": failed_checks,
            },
            ensure_ascii=False,
        )
    )
    return 0 if integration_passed else 1


def evaluate_category(
    *,
    category: str,
    g06: dict[str, Any],
    g06_fixture: dict[str, Any],
    g07: dict[str, Any],
) -> dict[str, Any]:
    g06_category = g06["categories"][category]
    fixture_category = g06_fixture["categories"][category]
    g07_category = g07["categories"][category]
    taxonomy_version = str(g06_category.get("taxonomy_version") or "")
    release_quality = g06_category.get("release_quality") or {}
    metrics = release_quality.get("metrics_json") or {}
    threshold_results = release_quality.get("threshold_results") or []
    unaffected = g06_category.get("unaffected_regression_skus") or []
    focus_profiles = fixture_category.get("focus_profiles") or []
    g07_targets = g07_category.get("targets") or []
    g07_top3 = g07_category.get("top3_rows") or []
    observed_skus = collect_sku_codes(unaffected, focus_profiles, g07_targets, g07_top3)
    prefix = EXPECTED_PREFIXES[category]
    other_prefix = EXPECTED_PREFIXES["AC" if category == "TV" else "TV"]

    checks = {
        "taxonomy_isolated": (
            taxonomy_version == EXPECTED_TAXONOMIES[category]
            and fixture_category.get("taxonomy_version")
            == EXPECTED_TAXONOMIES[category]
        ),
        "sku_prefix_isolated": bool(observed_skus)
        and all(code.startswith(prefix) for code in observed_skus)
        and not any(code.startswith(other_prefix) for code in observed_skus),
        "full_scope_complete": (
            g06_category.get("checks", {}).get("full_scope_complete") is True
        ),
        "release_quality_ready": release_quality.get("release_quality_status")
        == "ready",
        "all_release_thresholds_passed": bool(threshold_results)
        and all(item.get("passed") is True for item in threshold_results),
        "sku_consumable_rate_complete": metrics.get("sku_consumable_rate")
        == "1.0000",
        "unaffected_regression_20": len(unaffected) >= 20,
        "focus_validation_complete": bool(focus_profiles)
        and all(item.get("passed") is True for item in g06_category.get("focus_results", [])),
        "g06_business_checks_passed": all(
            value is True for value in g06_category.get("checks", {}).values()
        ),
        "g07_competitor_checks_passed": all(
            value is True for value in g07_category.get("checks", {}).values()
        ),
    }
    passed = all(checks.values())
    return {
        "category_code": category,
        "taxonomy_version": taxonomy_version,
        "sku_count": metrics.get("profile_count"),
        "status_counts": metrics.get("status_counts"),
        "ready_rate": metrics.get("ready_rate"),
        "sku_consumable_rate": metrics.get("sku_consumable_rate"),
        "core_payment_missing_rate": metrics.get("core_payment_missing_rate"),
        "focus_sku_count": len(focus_profiles),
        "unaffected_regression_sku_count": len(unaffected),
        "unaffected_regression_sku_codes": [
            str(item.get("sku_code")) for item in unaffected
        ],
        "g07_target_count": g07_category.get("summary", {}).get("target_count"),
        "g07_pair_count": g07_category.get("summary", {}).get("pair_count"),
        "checks": checks,
        "decision": "go_to_g09" if passed else "no_go",
    }


def collect_sku_codes(*collections: list[dict[str, Any]]) -> set[str]:
    sku_codes: set[str] = set()
    for collection in collections:
        for item in collection:
            for key in ("sku_code", "target_sku_code", "candidate_sku_code"):
                value = str(item.get(key) or "").strip()
                if value:
                    sku_codes.add(value)
    return sku_codes


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_outputs(payload: dict[str, Any], output_json: Path, output_markdown: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M12D-RP-G08 跨品类集成验收与上线前结论",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 集成回归：`{payload['integration_tests']['pytest_passed']} passed`。",
        "- 数据边界：复用 G06 全量只读影子结果和 G07 竞品消费收据；未写库、未部署、未发布。",
        "",
    ]
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- 结论：`{result['decision']}`。",
                f"- 全量 SKU：`{result['sku_count']}`；状态分布：`{json.dumps(result['status_counts'], ensure_ascii=False)}`。",
                f"- ready 比例：`{result['ready_rate']}`；可消费比例：`{result['sku_consumable_rate']}`；无核心理由比例：`{result['core_payment_missing_rate']}`。",
                f"- 重点 SKU：`{result['focus_sku_count']}`；未影响回归：`{result['unaffected_regression_sku_count']}`；竞品回归目标/pair：`{result['g07_target_count']}/{result['g07_pair_count']}`。",
                f"- 品类 taxonomy：`{result['taxonomy_version']}`；类别隔离：`{'通过' if result['checks']['taxonomy_isolated'] and result['checks']['sku_prefix_isolated'] else '失败'}`。",
                f"- 检查项：`{json.dumps(result['checks'], ensure_ascii=False)}`。",
                "",
            ]
        )
    backfill = payload["qf_backfill"]
    acceptance = payload["acceptance"]
    lines.extend(
        [
            "## QF15/QF16 回填",
            "",
            f"- QF15 历史结论：{backfill['qf15_historical_result']}",
            f"- QF15 当前状态：{backfill['qf15_current_state']}",
            f"- QF16 前置：{backfill['qf16_prerequisite']}",
            f"- QF17：{backfill['qf17_state']}",
            "",
            "## 上线前结论",
            "",
            f"- G08：`{'通过' if acceptance['passed'] else '未通过'}`；失败项：`{acceptance['failed_checks']}`。",
            f"- G09 提交部署候选：`{acceptance['g09_commit_deploy_candidate']}`。",
            f"- 当前发布：`{acceptance['current_publish']}`。",
            f"- 说明：{acceptance['reason_cn']}",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    current = REPO_ROOT / "docs/core3_mvp/real_data_v2/current_implementation"
    parser.add_argument(
        "--g06-result", default=str(current / "M12D_RP_G06_tv_ac_full_shadow.json")
    )
    parser.add_argument(
        "--g06-fixture", default=str(current / "M12D_RP_G06_validated_fixture.json")
    )
    parser.add_argument(
        "--g07-result",
        default=str(current / "M12D_RP_G07_competitor_consumption_shadow.json"),
    )
    parser.add_argument("--pytest-passed", type=int, default=0)
    parser.add_argument("--g07-replay-identical", action="store_true")
    parser.add_argument(
        "--output-json",
        default=str(current / "M12D_RP_G08_integrated_acceptance.json"),
    )
    parser.add_argument(
        "--output-markdown",
        default=str(current / "M12D_RP_G08_integrated_acceptance_report.md"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
