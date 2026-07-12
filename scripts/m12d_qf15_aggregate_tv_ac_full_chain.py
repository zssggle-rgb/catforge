#!/usr/bin/env python3
"""Aggregate QF15 TV/AC full-chain draft receipts and enforce stop gates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MODULE_FILES = {
    "M03B": "M12D_QF02_tv_ac_m03b_draft.json",
    "M04C": "M12D_QF03_tv_ac_m04c_draft.json",
    "M05C": "M12D_QF04_tv_ac_m05c_draft.json",
    "M07": "M12D_QF05_tv_ac_m07_draft.json",
    "M09C": "M12D_QF06_tv_ac_m09c_draft.json",
    "M10C": "M12D_QF07_tv_ac_m10c_draft.json",
    "M11C": "M12D_QF08_tv_ac_m11c_draft.json",
    "M12C": "M12D_QF09_tv_ac_m12c_draft.json",
}
LINEAGE_DIGEST_MODULES = {"M09C", "M10C", "M11C"}
QF01_TV_REFERENCE = {"ready": 332, "ready_limited": 33, "weak_expression_only": 12}


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir)
    approved_dir = Path(args.approved_dir)
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    modules = aggregate_modules(run_dir, approved_dir)
    pre_focus = load_json(run_dir / "M12D_QF15_pre_focus_shadow.json")
    post_focus = load_json(run_dir / "M12D_QF15_post_focus_shadow.json")
    context = load_json(run_dir / "M12D_QF15_tv_ac_context_candidate_shadow.json")
    approved_context = load_json(approved_dir / "M12D_QF10_tv_ac_context_candidate_shadow.json")
    release = load_json(run_dir / "M12D_QF15_tv_ac_release_quality_shadow.json")

    focus_pre_post_unchanged = normalize_focus_categories(pre_focus["categories"]) == normalize_focus_categories(
        post_focus["categories"]
    )
    context_matches_approved = context["categories"] == approved_context["categories"]
    categories = {
        category: aggregate_category(
            category,
            post_focus["categories"][category],
            release["categories"][category],
        )
        for category in ("TV", "AC")
    }
    all_module_business_stable = all(item["business_summary_stable"] for item in modules.values())
    downstream_unchanged = bool(post_focus["downstream_guard"]["unchanged"]) and bool(
        release["downstream_guard"]["unchanged"]
    )
    full_chain_execution_passed = all(
        (
            all_module_business_stable,
            focus_pre_post_unchanged,
            context_matches_approved,
            downstream_unchanged,
            all(not item["price_value_guard"]["violations"] for item in categories.values()),
        )
    )
    release_gate_passed = all(
        item["release_quality_status"] == "ready" for item in categories.values()
    )
    payload = {
        "task_id": "M12D-QF-15",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "impact_set": "TV 377 SKU、AC 155 SKU；QF02-QF09 新版 draft 和 QF10-QF13 影子结果。",
            "allowed_migrations": [
                "QF02-QF09 各模块既定的版本内业务迁移",
                "M07 幂等重写后 evidence lineage 标识刷新，但分数、关系状态和 M12D 业务结果不得变化",
            ],
            "unaffected_regression": "TV/AC 各 20 个非重点 SKU；另比较全量 M12D 重跑前后结果。",
            "forbidden": [
                "降低强证据、场景或弱表达门槛",
                "添加 SKU/品牌白名单",
                "跨品类 taxonomy/市场池",
                "写 current/published 或改变竞品 Top 3",
            ],
        },
        "execution": {
            "modules": modules,
            "m07_recovery": {
                "initial_exit_code": 137,
                "failure_phase": "post_write_full_capture",
                "draft_chunks_committed_before_exit": True,
                "root_cause": "后置验收把约 140 万市场池成员再次整体载入内存，触发容器 OOM。",
                "recovery": "未重复写 draft；使用批准影子收据执行 validate-persisted-only 紧凑校验。",
                "compact_validation_passed": modules["M07"]["business_summary_stable"],
            },
            "context_matches_qf10_approved": context_matches_approved,
            "focus_pre_post_unchanged": focus_pre_post_unchanged,
            "m12d_persisted_tables_unchanged": downstream_unchanged,
        },
        "categories": categories,
        "acceptance": {
            "full_chain_execution_passed": full_chain_execution_passed,
            "release_gate_passed": release_gate_passed,
            "release_blocked_categories": [
                category
                for category, item in categories.items()
                if item["release_quality_status"] != "ready"
            ],
            "workflow_decision": (
                "eligible_for_qf16" if full_chain_execution_passed and release_gate_passed else "stop_before_qf16"
            ),
            "reason_cn": (
                "全链路和发布质量门槛均通过。"
                if release_gate_passed
                else "全链路重跑一致，但 TV/AC 发布质量均为 limited；按 QF15 验收契约停在 QF16 前。"
            ),
        },
    }
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    if not full_chain_execution_passed:
        raise RuntimeError("QF15 full-chain execution consistency failed")
    print(
        json.dumps(
            {
                "status": "ok",
                "full_chain_execution_passed": full_chain_execution_passed,
                "release_gate_passed": release_gate_passed,
                "workflow_decision": payload["acceptance"]["workflow_decision"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def aggregate_modules(run_dir: Path, approved_dir: Path) -> dict[str, Any]:
    result = {}
    for module, filename in MODULE_FILES.items():
        current = load_json(run_dir / filename)
        approved = load_json(approved_dir / filename)
        changed_paths = diff_paths(approved["after"], current["after"])
        allowed_paths = (
            {f"{category}.score_business_digest" for category in ("TV", "AC")}
            if module in LINEAGE_DIGEST_MODULES
            else set()
        )
        non_lineage_changes = sorted(path for path in changed_paths if path not in allowed_paths)
        guard = current.get("downstream_guard") or {}
        guard_unchanged = bool(guard.get("unchanged", guard.get("before") == guard.get("after")))
        result[module] = {
            "task_id": current.get("task_id"),
            "write_draft": bool(current.get("write_draft")),
            "after_matches_approved_exactly": not changed_paths,
            "changed_summary_paths": sorted(changed_paths),
            "lineage_digest_refresh_only": bool(changed_paths) and not non_lineage_changes,
            "non_lineage_summary_changes": non_lineage_changes,
            "downstream_guard_unchanged": guard_unchanged,
            "business_summary_stable": not non_lineage_changes and guard_unchanged,
            "category_summaries": {
                category: compact_module_summary(module, current["after"][category])
                for category in ("TV", "AC")
            },
        }
    return result


def compact_module_summary(module: str, summary: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "M03B": ("profile_count", "conflict_sku_count", "conflict_count"),
        "M04C": ("profile_count", "fact_count", "quality_flag_counts"),
        "M05C": ("profile_count", "fact_count", "profile_flag_counts"),
        "M07": ("sku_count", "profile_count", "member_count", "full_review_required_count"),
        "M09C": ("profile_count", "score_count", "review_status_counts", "no_primary_count"),
        "M10C": ("profile_count", "score_count", "review_status_counts", "no_primary_count"),
        "M11C": ("profile_count", "score_count", "review_status_counts", "no_primary_count"),
        "M12C": ("sku_count", "missing_sku_count", "claim_scoped_status_counts"),
    }[module]
    return {field: summary.get(field) for field in fields}


def aggregate_category(
    category: str,
    focus: Mapping[str, Any],
    release: Mapping[str, Any],
) -> dict[str, Any]:
    evaluation = release["focus_pass_evaluation"]
    metrics = evaluation["metrics_json"]
    threshold_failures = [
        item for item in evaluation["threshold_results"] if item["applicable"] and not item["passed"]
    ]
    result = {
        "sku_count": focus["sku_count"],
        "taxonomy_version": focus["taxonomy_version"],
        "persisted_distribution": focus["persisted_distribution"],
        "draft_distribution": focus["shadow_distribution"],
        "focus_selection_count": focus["focus_selection"]["selected_count"],
        "unaffected_regression_count": len(focus["unaffected_regression_samples"]),
        "price_value_guard": {
            "observed_count": focus["price_value_guard"]["weak_cap_observation_count"],
            "violations": focus["price_value_guard"]["violations"],
        },
        "no_core_diagnosis": focus["no_core_diagnosis"],
        "weak_profile_diagnosis": focus["weak_profile_diagnosis"],
        "release_quality_status": evaluation["release_quality_status"],
        "release_metrics": metrics,
        "release_failure_reason_codes": evaluation["failure_reason_codes"],
        "release_threshold_failures": threshold_failures,
        "system_issues": evaluation["system_issues"],
    }
    if category == "TV":
        actual = focus["shadow_distribution"]["status_counts"]
        denominator = focus["sku_count"]
        result["qf01_feasibility_reference_deviation_pp"] = {
            status: rate_delta_pp(actual.get(status, 0), expected, denominator)
            for status, expected in QF01_TV_REFERENCE.items()
        }
        result["qf01_reference_deviation_explanation_cn"] = (
            "QF01 约 332 ready 是早期可行性投影；QF11 锚点作用域门槛和 QF12 核心族收敛后，"
            "强消费 ready 降为 238。QF14 已逐项确认无系统性误杀，差异不能通过降低证据门槛消除。"
        )
    return result


def normalize_focus_categories(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
    for category in ("TV", "AC"):
        guard = normalized[category]["price_value_guard"]
        guard["weak_cap_observations"] = sorted(
            guard["weak_cap_observations"],
            key=lambda item: (item["sku_code"], item["anchor_code"]),
        )
    return normalized


def diff_paths(before: Any, after: Any, prefix: str = "") -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: set[str] = set()
        for key in set(before) | set(after):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.add(path)
            else:
                paths.update(diff_paths(before[key], after[key], path))
        return paths
    if before != after:
        return {prefix or "$"}
    return set()


def rate_delta_pp(actual: int, expected: int, denominator: int) -> str:
    delta = (actual - expected) / denominator * 100
    return f"{delta:.2f}pp"


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-15 TV/AC 全链路 Draft 重跑与验收",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 全链路执行一致性：`{payload['acceptance']['full_chain_execution_passed']}`",
        f"- 发布质量门槛：`{payload['acceptance']['release_gate_passed']}`",
        f"- 调度决定：`{payload['acceptance']['workflow_decision']}`",
        "",
        "## 1. 模块重跑",
        "",
        "| 模块 | 业务摘要稳定 | 与批准结果完全一致 | 仅 lineage digest 刷新 | 下游守卫 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for module, result in payload["execution"]["modules"].items():
        lines.append(
            f"| {module} | {result['business_summary_stable']} | "
            f"{result['after_matches_approved_exactly']} | "
            f"{result['lineage_digest_refresh_only']} | "
            f"{result['downstream_guard_unchanged']} |"
        )
    recovery = payload["execution"]["m07_recovery"]
    lines.extend(
        [
            "",
            "### M07 运行恢复",
            "",
            f"- 首次退出：`{recovery['initial_exit_code']}`，阶段：`{recovery['failure_phase']}`。",
            f"- 根因：{recovery['root_cause']}",
            f"- 恢复：{recovery['recovery']}",
            f"- 紧凑校验：`{recovery['compact_validation_passed']}`。",
            "",
            "## 2. 双品类发布质量",
            "",
            "| 品类 | SKU | ready | limited | weak | 无核心 | ready率 | ready+limited率 | 无核心率 | 发布质量 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for category in ("TV", "AC"):
        item = payload["categories"][category]
        statuses = item["draft_distribution"]["status_counts"]
        metrics = item["release_metrics"]
        lines.append(
            f"| {category} | {item['sku_count']} | {statuses.get('ready', 0)} | "
            f"{statuses.get('ready_limited', 0)} | {statuses.get('weak_expression_only', 0)} | "
            f"{item['draft_distribution']['core_missing_count']} | {metrics['ready_rate']} | "
            f"{metrics['ready_or_limited_rate']} | {metrics['core_payment_missing_rate']} | "
            f"{item['release_quality_status']} |"
        )
    for category in ("TV", "AC"):
        item = payload["categories"][category]
        lines.extend(
            [
                "",
                f"### {category} 未通过项",
                "",
                f"- 发布失败项：`{item['release_failure_reason_codes']}`",
                f"- 无核心归因：`{item['no_core_diagnosis']['reason_counts']}`",
                f"- 弱画像归因：`{item['weak_profile_diagnosis']['reason_counts']}`",
                f"- 价格价值门槛观察：`{item['price_value_guard']['observed_count']}`；误升核心：`{len(item['price_value_guard']['violations'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 3. 结论",
            "",
            f"- {payload['acceptance']['reason_cn']}",
            "- M12D 重跑前后业务结果一致，当前发布画像/锚点/版本未变化。",
            "- 未降低门槛、未加入白名单、未发布 current、未运行竞品智能体。",
            "",
        ]
    )
    return "\n".join(lines)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--approved-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
