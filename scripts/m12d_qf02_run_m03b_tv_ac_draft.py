#!/usr/bin/env python3
"""Run and compare TV/AC M03B v0.2 drafts without touching downstream modules."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_PARSER_VERSION,
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_PARSER_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.m03b_param_profile_service import (
    M03BParamEvidenceReader,
    M03BProfileBuilder,
    M03BRunner,
    M03BTaxonomyLoader,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
TV_BATCH_IDS = (
    "m00_20260613004311_d548f6dc",
    "m00_20260619084551_857df63b",
)
AC_BATCH_IDS = ("m00_20260624000202_1150a669",)

CATEGORY_CONFIG = {
    "TV": {
        "batch_ids": TV_BATCH_IDS,
        "sku_prefix": "TV",
        "old_rule_version": "m03b_tv_param_profile_v0.1",
        "old_taxonomy_version": "tv_param_taxonomy_manual_v0.1",
        "rule_version": CORE3_M03B_RULE_VERSION,
        "taxonomy_version": CORE3_M03B_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_PARSER_VERSION,
        "allowed_profile_additions": set(),
    },
    "AC": {
        "batch_ids": AC_BATCH_IDS,
        "sku_prefix": "AC",
        "old_rule_version": "m03b_ac_param_profile_v0.1",
        "old_taxonomy_version": "ac_param_taxonomy_manual_v0.1",
        "rule_version": CORE3_M03B_AC_RULE_VERSION,
        "taxonomy_version": CORE3_M03B_AC_TAXONOMY_VERSION,
        "parser_version": CORE3_M03B_AC_PARSER_VERSION,
        "allowed_profile_additions": {"brand_series_code"},
    },
}

DOWNSTREAM_TABLES = (
    "core3_sku_claim_fact_profile",
    "core3_sku_comment_fact_profile",
    "core3_sku_market_profile",
    "core3_m09c_sku_user_task_profile",
    "core3_m10c_sku_target_group_profile",
    "core3_sku_value_battlefield_profile",
    "core3_sku_claim_value_quantification",
    "core3_sku_purchase_reason_profile",
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        downstream_before = capture_downstream_guard(db)
        before = {category: capture_category(db, category, use_new=False) for category in CATEGORY_CONFIG}
        run_results: dict[str, list[dict[str, Any]]] = {"TV": [], "AC": []}
        if args.write_draft:
            for category, config in CATEGORY_CONFIG.items():
                for batch_id in config["batch_ids"]:
                    result = M03BRunner(db).run_batch(
                        project_id=PROJECT_ID,
                        category_code=category,
                        batch_id=batch_id,
                        taxonomy_version=config["taxonomy_version"],
                        parser_version=config["parser_version"],
                        rule_version=config["rule_version"],
                        force_rebuild=False,
                        sku_code_prefix=config["sku_prefix"],
                    )
                    status = result.status.value if hasattr(result.status, "value") else str(result.status)
                    if status not in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value}:
                        db.rollback()
                        raise RuntimeError(f"{category} M03B draft failed for {batch_id}: {result.summary_json}")
                    db.commit()
                    run_results[category].append(
                        {
                            "batch_id": batch_id,
                            "status": status,
                            "input_count": result.input_count,
                            "output_count": result.output_count,
                            "warnings": list(result.warnings),
                            "summary": result.summary_json,
                        }
                    )
        after = {
            category: capture_category(db, category, use_new=True)
            if args.write_draft
            else capture_shadow_category(db, category)
            for category in CATEGORY_CONFIG
        }
        downstream_after = capture_downstream_guard(db)

    comparisons = {
        category: compare_category(before[category], after[category], category)
        for category in CATEGORY_CONFIG
    }
    payload = {
        "task_id": "M12D-QF-02",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "write_draft": args.write_draft,
        "scope": "M03B only",
        "allowed_migrations": {
            "TV": [
                "screen_size_segment semantic-equivalent conflict_count 1 -> 0",
                "M03B version metadata v0.1 -> v0.2",
            ],
            "AC": [
                "product_series false conflict_count 1 -> 0",
                "brand_series_code added while product_series remains the series name",
                "known_param_count may increase by one for the separated series code",
                "M03B version metadata v0.1 -> v0.2",
            ],
        },
        "before": {category: compact_capture(value) for category, value in before.items()},
        "after": {category: compact_capture(value) for category, value in after.items()},
        "comparisons": comparisons,
        "run_results": run_results,
        "downstream_guard": {
            "before": downstream_before,
            "after": downstream_after,
            "unchanged": downstream_before == downstream_after,
        },
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"status": "ok", "output_json": str(output_json), "output_markdown": str(output_markdown), "comparisons": comparisons, "downstream_unchanged": downstream_before == downstream_after}, ensure_ascii=False, default=str))
    return 0


def capture_category(db, category: str, *, use_new: bool) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    rule_version = config["rule_version"] if use_new else config["old_rule_version"]
    taxonomy_version = config["taxonomy_version"] if use_new else config["old_taxonomy_version"]
    profiles = list(
        db.execute(
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == PROJECT_ID)
            .where(entities.Core3SkuParamProfile.category_code == category)
            .where(entities.Core3SkuParamProfile.batch_id.in_(config["batch_ids"]))
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .order_by(entities.Core3SkuParamProfile.batch_id, entities.Core3SkuParamProfile.sku_code)
        ).scalars()
    )
    tiers = list(
        db.execute(
            select(entities.Core3SkuParamDimensionTier)
            .where(entities.Core3SkuParamDimensionTier.project_id == PROJECT_ID)
            .where(entities.Core3SkuParamDimensionTier.category_code == category)
            .where(entities.Core3SkuParamDimensionTier.batch_id.in_(config["batch_ids"]))
            .where(entities.Core3SkuParamDimensionTier.taxonomy_version == taxonomy_version)
            .order_by(
                entities.Core3SkuParamDimensionTier.batch_id,
                entities.Core3SkuParamDimensionTier.sku_code,
                entities.Core3SkuParamDimensionTier.dimension_code,
            )
        ).scalars()
    )
    profile_rows = {f"{row.batch_id}:{row.sku_code}": profile_snapshot(row) for row in profiles}
    tier_rows = {
        f"{row.batch_id}:{row.sku_code}:{row.dimension_code}": row.tier_code
        for row in tiers
    }
    tier_distribution = Counter(
        f"{row.dimension_code}:{row.tier_code}"
        for row in tiers
    )
    conflict_param_counts: Counter[str] = Counter()
    for row in profiles:
        for item in (row.quality_summary_json or {}).get("conflicts", []):
            conflict_param_counts[str(item.get("param_code") or "unknown")] += 1
    return {
        "rule_version": rule_version,
        "taxonomy_version": taxonomy_version,
        "profile_count": len(profiles),
        "conflict_sku_count": sum(1 for row in profiles if row.conflict_count > 0),
        "conflict_count": sum(row.conflict_count for row in profiles),
        "conflict_param_counts": dict(sorted(conflict_param_counts.items())),
        "tier_distribution": dict(sorted(tier_distribution.items())),
        "profiles": profile_rows,
        "tiers": tier_rows,
    }


def capture_shadow_category(db, category: str) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    context = Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    taxonomy = M03BTaxonomyLoader().load(config["taxonomy_version"], category_code=category)
    profile_rows: dict[str, dict[str, Any]] = {}
    tier_rows: dict[str, str] = {}
    conflict_param_counts: Counter[str] = Counter()
    tier_distribution: Counter[str] = Counter()
    for batch_id in config["batch_ids"]:
        evidence = M03BParamEvidenceReader(context).list_param_raw_evidence(
            batch_id,
            sku_code_prefix=config["sku_prefix"],
        )
        _, profiles, tiers, _, _ = M03BProfileBuilder(
            project_id=PROJECT_ID,
            category_code=category,
            batch_id=batch_id,
            taxonomy=taxonomy,
            parser_version=config["parser_version"],
            rule_version=config["rule_version"],
            sku_code_prefix=config["sku_prefix"],
        ).build(evidence)
        for profile in profiles:
            payload = profile.to_record_payload()
            profile_rows[f"{batch_id}:{payload['sku_code']}"] = profile_snapshot_payload(payload)
            for item in (payload.get("quality_summary_json") or {}).get("conflicts", []):
                conflict_param_counts[str(item.get("param_code") or "unknown")] += 1
        for tier in tiers:
            payload = tier.to_record_payload()
            tier_rows[f"{batch_id}:{payload['sku_code']}:{payload['dimension_code']}"] = payload["tier_code"]
            tier_distribution[f"{payload['dimension_code']}:{payload['tier_code']}"] += 1
    return {
        "rule_version": config["rule_version"],
        "taxonomy_version": config["taxonomy_version"],
        "profile_count": len(profile_rows),
        "conflict_sku_count": sum(1 for row in profile_rows.values() if row["conflict_count"] > 0),
        "conflict_count": sum(row["conflict_count"] for row in profile_rows.values()),
        "conflict_param_counts": dict(sorted(conflict_param_counts.items())),
        "tier_distribution": dict(sorted(tier_distribution.items())),
        "profiles": profile_rows,
        "tiers": tier_rows,
    }


def profile_snapshot(row: entities.Core3SkuParamProfile) -> dict[str, Any]:
    return {
        "batch_id": row.batch_id,
        "sku_code": row.sku_code,
        "conflict_count": row.conflict_count,
        "known_param_count": row.known_param_count,
        "unknown_param_count": row.unknown_param_count,
        "param_completeness": str(row.param_completeness),
        "param_values_json": copy.deepcopy(row.param_values_json or {}),
    }


def profile_snapshot_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": row["batch_id"],
        "sku_code": row["sku_code"],
        "conflict_count": int(row["conflict_count"]),
        "known_param_count": int(row["known_param_count"]),
        "unknown_param_count": int(row["unknown_param_count"]),
        "param_completeness": str(row["param_completeness"]),
        "param_values_json": copy.deepcopy(row.get("param_values_json") or {}),
    }


def compare_category(before: dict[str, Any], after: dict[str, Any], category: str) -> dict[str, Any]:
    common_keys = sorted(set(before["profiles"]) & set(after["profiles"]))
    missing_after = sorted(set(before["profiles"]) - set(after["profiles"]))
    extra_after = sorted(set(after["profiles"]) - set(before["profiles"]))
    business_changed: list[str] = []
    completeness_changed: list[str] = []
    known_count_delta: Counter[int] = Counter()
    conflict_migrations: Counter[str] = Counter()
    for key in common_keys:
        old = before["profiles"][key]
        new = after["profiles"][key]
        if normalize_business_values(old["param_values_json"], category) != normalize_business_values(new["param_values_json"], category):
            business_changed.append(key)
        if old["param_completeness"] != new["param_completeness"]:
            completeness_changed.append(key)
        known_count_delta[new["known_param_count"] - old["known_param_count"]] += 1
        conflict_migrations[f"{old['conflict_count']}->{new['conflict_count']}"] += 1
    tier_keys = sorted(set(before["tiers"]) | set(after["tiers"]))
    tier_changed = [key for key in tier_keys if before["tiers"].get(key) != after["tiers"].get(key)]
    affected_keys = [key for key in common_keys if before["profiles"][key]["conflict_count"] > 0]
    unaffected_keys = [key for key in common_keys if before["profiles"][key]["conflict_count"] == 0]
    regression_pool = unaffected_keys if unaffected_keys else common_keys
    return {
        "common_profile_count": len(common_keys),
        "missing_after_count": len(missing_after),
        "extra_after_count": len(extra_after),
        "business_profile_changed_count": len(business_changed),
        "business_profile_changed_sample": business_changed[:20],
        "completeness_changed_count": len(completeness_changed),
        "tier_changed_count": len(tier_changed),
        "tier_changed_sample": tier_changed[:20],
        "known_param_count_delta_distribution": {str(key): value for key, value in sorted(known_count_delta.items())},
        "conflict_migration_distribution": dict(sorted(conflict_migrations.items())),
        "affected_profile_count": len(affected_keys),
        "affected_profile_sample": affected_keys[:20],
        "unaffected_regression_pool_count": len(regression_pool),
        "unaffected_regression_sample": regression_pool[:20],
    }


def normalize_business_values(values: dict[str, Any], category: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for param_code, entry in values.items():
        if param_code in {"_metadata", "tier_explanation"}:
            continue
        if category == "AC" and param_code == "brand_series_code":
            continue
        if param_code == "dimension_tier_profile":
            normalized[param_code] = copy.deepcopy(entry)
            continue
        if not isinstance(entry, dict):
            normalized[param_code] = copy.deepcopy(entry)
            continue
        normalized[param_code] = {
            "normalized_value": copy.deepcopy(entry.get("normalized_value")),
            "numeric_value": entry.get("numeric_value"),
            "value_presence": entry.get("value_presence"),
        }
    return normalized


def compact_capture(capture: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in capture.items()
        if key not in {"profiles", "tiers"}
    }


def capture_downstream_guard(db) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(text(f"SELECT count(*) AS row_count, max(updated_at) AS max_updated_at FROM {table_name}")).mappings().one()
        result[table_name] = {
            "row_count": int(row["row_count"]),
            "max_updated_at": row["max_updated_at"].isoformat() if row["max_updated_at"] else None,
        }
    return result


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M12D-QF-02 M03B TV/AC Draft Rerun Report",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Project: `{payload['project_id']}`",
        f"- Scope: `{payload['scope']}`",
        f"- Draft write: `{payload['write_draft']}`",
        f"- Downstream tables unchanged: `{payload['downstream_guard']['unchanged']}`",
        "",
    ]
    for category in ("TV", "AC"):
        before = payload["before"][category]
        after = payload["after"][category]
        comparison = payload["comparisons"][category]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- Profiles: `{before['profile_count']} -> {after['profile_count']}`",
                f"- Conflict SKUs: `{before['conflict_sku_count']} -> {after['conflict_sku_count']}`",
                f"- Conflicts: `{before['conflict_count']} -> {after['conflict_count']}`",
                f"- New conflict params: `{json.dumps(after['conflict_param_counts'], ensure_ascii=False)}`",
                f"- Business profile changes outside allowance: `{comparison['business_profile_changed_count']}`",
                f"- Tier changes: `{comparison['tier_changed_count']}`",
                f"- Completeness changes: `{comparison['completeness_changed_count']}`",
                f"- Conflict migrations: `{json.dumps(comparison['conflict_migration_distribution'], ensure_ascii=False)}`",
                f"- Known-param count deltas: `{json.dumps(comparison['known_param_count_delta_distribution'], ensure_ascii=False)}`",
                f"- Affected profiles: `{comparison['affected_profile_count']}`",
                f"- Regression pool: `{comparison['unaffected_regression_pool_count']}`",
                f"- Regression sample: `{', '.join(comparison['unaffected_regression_sample'])}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-draft", action="store_true")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
