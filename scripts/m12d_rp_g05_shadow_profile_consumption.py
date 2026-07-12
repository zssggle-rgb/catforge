#!/usr/bin/env python3
"""Read-only G05 shadow using the accepted G04 full-anchor evidence fixture."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.core3_real_data.constants import (  # noqa: E402
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    M12DAnchorRole,
    M12DProfileStatus,
    M12DPurchasePressureLevel,
    M12DReasonEstablishmentStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (  # noqa: E402
    M12DAnchorTaxonomyLoader,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (  # noqa: E402
    M12DScoredPurchaseReasonAnchor,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (  # noqa: E402
    ReasonRoleClassifier,
    _converge_core_anchors,
    _profile_confidence,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
TAXONOMY_VERSIONS = {
    "TV": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    "AC": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
}
DOWNSTREAM_TABLES = (
    "core3_sku_purchase_reason_profile",
    "core3_sku_purchase_reason_anchor",
    "core3_purchase_reason_profile_version",
)
ESTABLISHED = {
    M12DReasonEstablishmentStatus.ESTABLISHED.value,
    M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
}
HIGH_PRESSURE = {
    M12DPurchasePressureLevel.HIGH.value,
    M12DPurchasePressureLevel.CRITICAL.value,
}


def main() -> int:
    args = parse_args()
    source = json.loads(Path(args.g04_json).read_text(encoding="utf-8"))
    engine = create_engine(args.database_url, future=True, pool_pre_ping=True)
    with engine.connect() as connection:
        before = capture_guard(connection)
        categories = {
            category: shadow_category(
                connection, category, source["categories"][category]
            )
            for category in ("TV", "AC")
        }
        after = capture_guard(connection)
    engine.dispose()

    failed_checks: list[str] = []
    if before != after:
        failed_checks.append("downstream_tables_changed")
    for category, result in categories.items():
        summary = result["summary"]
        for field in (
            "eligible_reason_lost_to_pressure_count",
            "proposition_selected_as_core_count",
            "core_below_7_count",
            "ready_without_core_count",
            "unclassified_sku_count",
        ):
            if summary[field]:
                failed_checks.append(f"{category.lower()}_{field}")
        if len(result["unaffected_regression_skus"]) < 20:
            failed_checks.append(f"{category.lower()}_unaffected_regression_below_20")

    payload = {
        "task_id": "M12D-RP-G05",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "method": {
            "evidence_input": "复用 G04 已验收的 TV/AC 全量成立度、用户承接和压力锚点。",
            "live_baseline": "只读 205 当前 published profile/version，比较旧角色与 SKU 状态。",
            "decision": "成立状态决定角色；压力并行；每 SKU 最多三条核心且理由族去重。",
            "consumption": "版本 blocked 才全局阻断；ready/limited 版本均按 SKU 的 strong/limited/facts_only 能力消费。",
        },
        "categories": categories,
        "downstream_guard": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "acceptance": {"passed": not failed_checks, "failed_checks": failed_checks},
    }
    write_outputs(args, payload)
    print(
        json.dumps(
            {
                "status": "ok" if not failed_checks else "failed",
                "categories": {
                    category: result["summary"]
                    for category, result in categories.items()
                },
                "downstream_unchanged": before == after,
                "failed_checks": failed_checks,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failed_checks else 1


def shadow_category(
    connection: Any, category: str, g04: dict[str, Any]
) -> dict[str, Any]:
    version_id = str(g04["purchase_reason_version_id"])
    baseline = current_profiles(connection, category, version_id)
    version_quality = current_version_quality(connection, category, version_id)
    taxonomy = M12DAnchorTaxonomyLoader().load(
        TAXONOMY_VERSIONS[category], product_category=category
    )
    definitions = {
        item.purchase_reason_code: item for item in taxonomy.purchase_reasons
    }
    rows_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in g04["anchors"]:
        rows_by_sku[str(row["sku_code"])].append(row)

    role_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    consumption_counts: Counter[str] = Counter()
    pressure_core_counts: Counter[str] = Counter()
    migrations: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    lost_to_pressure: list[dict[str, str]] = []
    proposition_core: list[dict[str, str]] = []
    core_below_7: list[dict[str, str]] = []
    ready_without_core: list[str] = []

    for sku_code, rows in sorted(rows_by_sku.items()):
        anchors = []
        for row in rows:
            definition = definitions[str(row["anchor_code"])]
            anchor = anchor_from_g04(category, definition, row)
            anchors.append(ReasonRoleClassifier().classify(anchor))
        converged, selected_core = _converge_core_anchors(anchors)
        core_codes = [anchor.anchor_code for anchor in selected_core]
        established_codes = [
            anchor.anchor_code
            for anchor in converged
            if str(anchor.establishment_status) in ESTABLISHED
        ]
        proposition_codes = [
            anchor.anchor_code
            for anchor in converged
            if str(anchor.establishment_status)
            == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
        ]
        if core_codes:
            status = M12DProfileStatus.READY.value
            consumption_mode = "strong"
        elif established_codes:
            status = M12DProfileStatus.READY_LIMITED.value
            consumption_mode = "limited"
        elif proposition_codes:
            status = M12DProfileStatus.READY_LIMITED.value
            consumption_mode = "facts_only"
        else:
            status = M12DProfileStatus.WEAK_EXPRESSION_ONLY.value
            consumption_mode = "facts_only"
        confidence, _ = _profile_confidence(selected_core)

        status_counts[status] += 1
        consumption_counts[consumption_mode] += 1
        role_counts.update(str(anchor.role) for anchor in converged)
        baseline_row = baseline.get(sku_code, {})
        old_status = str(baseline_row.get("status") or "missing")
        old_core = list(baseline_row.get("core_payment_anchors") or [])
        if old_status != status or old_core != core_codes:
            migrations.append(
                {
                    "sku_code": sku_code,
                    "old_status": old_status,
                    "new_status": status,
                    "old_core": old_core,
                    "new_core": core_codes,
                }
            )
        if status == M12DProfileStatus.READY.value and not core_codes:
            ready_without_core.append(sku_code)

        for anchor in converged:
            pressure = str(anchor.pressure_level)
            if anchor.anchor_code in core_codes and pressure in HIGH_PRESSURE:
                pressure_core_counts[pressure] += 1
            if (
                anchor.core_eligible is True
                and pressure in HIGH_PRESSURE
                and anchor.role
                in {
                    M12DAnchorRole.WEAK_EXPRESSION.value,
                    M12DAnchorRole.RISK_DRAG.value,
                }
            ):
                lost_to_pressure.append(
                    {"sku_code": sku_code, "anchor_code": anchor.anchor_code}
                )
            if (
                str(anchor.establishment_status)
                == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
                and anchor.anchor_code in core_codes
            ):
                proposition_core.append(
                    {"sku_code": sku_code, "anchor_code": anchor.anchor_code}
                )
            if anchor.anchor_code in core_codes and Decimal(
                str(anchor.establishment_score or 0)
            ) < Decimal("7"):
                core_below_7.append(
                    {"sku_code": sku_code, "anchor_code": anchor.anchor_code}
                )
        result_rows.append(
            {
                "category": category,
                "sku_code": sku_code,
                "old_status": old_status,
                "new_status": status,
                "old_core_count": len(old_core),
                "new_core_count": len(core_codes),
                "new_core_codes": core_codes,
                "established_count": len(established_codes),
                "proposition_count": len(proposition_codes),
                "profile_confidence": str(confidence),
                "consumption_mode": consumption_mode,
            }
        )

    migration_skus = {row["sku_code"] for row in migrations}
    exact_unchanged = [
        row for row in result_rows if row["sku_code"] not in migration_skus
    ]
    unaffected = result_rows[:20]
    status_transitions = Counter(
        f"{row['old_status']}->{row['new_status']}" for row in migrations
    )
    core_count_deltas = Counter(
        str(len(row["new_core"]) - len(row["old_core"])) for row in migrations
    )
    return {
        "purchase_reason_version_id": version_id,
        "taxonomy_version": TAXONOMY_VERSIONS[category],
        "release_quality_status": version_quality,
        "summary": {
            "sku_count": len(result_rows),
            "role_counts": dict(sorted(role_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "consumption_mode_counts": dict(sorted(consumption_counts.items())),
            "status_or_core_migration_sku_count": len(migration_skus),
            "exact_status_core_unchanged_sku_count": len(exact_unchanged),
            "status_transition_counts": dict(sorted(status_transitions.items())),
            "core_count_delta_counts": dict(sorted(core_count_deltas.items())),
            "selected_high_pressure_core_counts": dict(
                sorted(pressure_core_counts.items())
            ),
            "eligible_reason_lost_to_pressure_count": len(lost_to_pressure),
            "proposition_selected_as_core_count": len(proposition_core),
            "core_below_7_count": len(core_below_7),
            "ready_without_core_count": len(ready_without_core),
            "unclassified_sku_count": len(set(baseline) - set(rows_by_sku)),
            "unaffected_regression_sku_count": len(unaffected),
        },
        "impact_skus": sorted(migration_skus),
        "allowed_migration": [
            "anchor role",
            "core family/top3 convergence",
            "profile confidence",
            "SKU status",
            "SKU consumption mode",
        ],
        "preserved_regression_fields": [
            "G04 establishment_status/score",
            "G04 user_validation_status/core_eligible",
            "G03 pressure_level",
            "taxonomy_version",
        ],
        "migrations": migrations,
        "unaffected_regression_skus": unaffected,
        "rows": result_rows,
        "invalid_samples": {
            "lost_to_pressure": lost_to_pressure[:20],
            "proposition_core": proposition_core[:20],
            "core_below_7": core_below_7[:20],
            "ready_without_core": ready_without_core[:20],
        },
    }


def anchor_from_g04(
    category: str, definition: Any, row: dict[str, Any]
) -> M12DScoredPurchaseReasonAnchor:
    return M12DScoredPurchaseReasonAnchor(
        taxonomy_version=TAXONOMY_VERSIONS[category],
        product_category=category,
        sku_code=str(row["sku_code"]),
        anchor_code=str(row["anchor_code"]),
        anchor_cn=str(row["anchor_cn"]),
        anchor_family_code=definition.purchase_reason_family_code,
        anchor_family_cn=definition.purchase_reason_family_cn,
        anchor_rank=int(definition.candidate_rank),
        role=row["legacy_role"],
        evidence_strength="medium",
        confidence=Decimal("0.7000"),
        establishment_status=row["establishment_status"],
        establishment_score=Decimal(str(row["establishment_score"])),
        establishment_domains_json=row["establishment_domains"],
        user_validation_status=row["user_validation_status"],
        core_eligible=bool(row["core_eligible"]),
        core_ineligible_reasons_json=row["core_ineligible_reasons"],
        pressure_level=row["pressure_level"],
        adjusted_evidence_score=Decimal(str(row["legacy_adjusted_score"])),
        support_summary_cn="G04 已验收正向成立证据。",
        role_reason_json={
            "establishment_strong_domain_count": sum(
                domain
                in {
                    "param_fact",
                    "comment_perception",
                    "claim_value",
                    "market_acceptance",
                }
                for domain in row["establishment_domains"]
            ),
            "establishment_threshold_path": row["threshold_path"],
        },
        input_fingerprint=f"g04-{category}-{row['sku_code']}-{row['anchor_code']}",
    )


def current_profiles(
    connection: Any, category: str, version_id: str
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        text(
            "SELECT sku_code, status, core_payment_anchors_json "
            "FROM core3_sku_purchase_reason_profile "
            "WHERE project_id=:project_id AND category_code=:category "
            "AND purchase_reason_version_id=:version_id AND is_current IS TRUE"
        ),
        {"project_id": PROJECT_ID, "category": category, "version_id": version_id},
    )
    return {
        str(row.sku_code): {
            "status": str(row.status),
            "core_payment_anchors": list(row.core_payment_anchors_json or []),
        }
        for row in rows
    }


def current_version_quality(connection: Any, category: str, version_id: str) -> str:
    has_column = connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='core3_purchase_reason_profile_version' "
            "AND column_name='release_quality_status')"
        )
    ).scalar_one()
    if not has_column:
        return "legacy_unassessed"
    row = connection.execute(
        text(
            "SELECT release_quality_status FROM core3_purchase_reason_profile_version "
            "WHERE project_id=:project_id AND category_code=:category "
            "AND purchase_reason_version_id=:version_id"
        ),
        {"project_id": PROJECT_ID, "category": category, "version_id": version_id},
    ).first()
    return str(row.release_quality_status if row else "missing")


def capture_guard(connection: Any) -> dict[str, dict[str, Any]]:
    result = {}
    for table in DOWNSTREAM_TABLES:
        row = connection.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table}")
        ).one()
        result[table] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def write_outputs(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    json_path = Path(args.output_json)
    csv_path = Path(args.output_csv)
    markdown_path = Path(args.output_markdown)
    fixture_path = Path(args.output_fixture)
    for path in (json_path, csv_path, markdown_path, fixture_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = list(payload["categories"]["TV"]["rows"][0])
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for category in ("TV", "AC"):
            for row in payload["categories"][category]["rows"]:
                writer.writerow(
                    {**row, "new_core_codes": "|".join(row["new_core_codes"])}
                )
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    fixture = {
        "contract_version": "m12d_reason_pressure_consumption_v0.1",
        "task_id": payload["task_id"],
        "rules": {
            "strong": "ready SKU 可比较已成立核心购买理由和压力。",
            "limited": "有已成立 supporting 理由，只能有限比较，不输出强替代结论。",
            "facts_only": "可比较参数、卖点、市场和产品价值主张，不比较用户购买理由。",
            "blocked": "仅版本 blocked 或 SKU failed/missing_input 时不可消费。",
        },
        "categories": {
            category: {
                "release_quality_status": result["release_quality_status"],
                "sku_count": result["summary"]["sku_count"],
                "consumption_mode_counts": result["summary"]["consumption_mode_counts"],
                "sample_skus": {
                    mode: next(
                        (
                            row["sku_code"]
                            for row in result["rows"]
                            if row["consumption_mode"] == mode
                        ),
                        None,
                    )
                    for mode in ("strong", "limited", "facts_only")
                },
            }
            for category, result in payload["categories"].items()
        },
    }
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M12D-RP-G05 TV/AC 画像与按 SKU 消费影子测算",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 证据输入：复用 G04 全量已验收锚点；205 数据库仅用于读取当前发布基线和写入保护快照。",
        "- 角色口径：成立状态决定角色；购买阻力不删除已成立理由。",
        "",
    ]
    for category, result in payload["categories"].items():
        summary = result["summary"]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- 当前版本质量：`{result['release_quality_status']}`；SKU：`{summary['sku_count']}`。",
                f"- 新 SKU 状态：`{json.dumps(summary['status_counts'], ensure_ascii=False)}`。",
                f"- 消费能力：`{json.dumps(summary['consumption_mode_counts'], ensure_ascii=False)}`。",
                f"- 状态或核心理由迁移：`{summary['status_or_core_migration_sku_count']}` SKU。",
                f"- 状态迁移：`{json.dumps(summary['status_transition_counts'], ensure_ascii=False)}`；核心条数变化：`{json.dumps(summary['core_count_delta_counts'], ensure_ascii=False)}`。",
                f"- 状态与核心完全不变：`{summary['exact_status_core_unchanged_sku_count']}` SKU；非目标字段回归样本：`{summary['unaffected_regression_sku_count']}`。",
                f"- 入选核心且带高/严重压力：`{json.dumps(summary['selected_high_pressure_core_counts'], ensure_ascii=False)}`；因普通压力丢失核心资格：`{summary['eligible_reason_lost_to_pressure_count']}`。",
                f"- proposition 误入核心：`{summary['proposition_selected_as_core_count']}`；低于 7 分核心：`{summary['core_below_7_count']}`。",
                "",
            ]
        )
    lines.extend(
        [
            "## 验收",
            "",
            f"- 三张 M12D 表前后快照一致：`{payload['downstream_guard']['unchanged']}`。",
            f"- G05 验收：`{'通过' if payload['acceptance']['passed'] else '未通过'}`。",
            f"- 未通过项：`{payload['acceptance']['failed_checks']}`。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--g04-json",
        default=str(
            REPO_ROOT
            / "docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G04_tv_ac_establishment_shadow.json"
        ),
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-fixture", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
