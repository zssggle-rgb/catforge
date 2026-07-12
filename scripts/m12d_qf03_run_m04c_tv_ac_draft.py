#!/usr/bin/env python3
"""Shadow, write, and compare TV/AC M04C v0.2 drafts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.m04c_claim_fact_profile_service import (
    INPUT_SOURCE_EVIDENCE,
    INPUT_SOURCE_RAW,
    M04CProfileBuilder,
    M04CRunner,
    M04CService,
    M04CTaxonomyLoader,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CONFIG = {
    "TV": {
        "batch_id": "m00_20260623014631_c8630747",
        "product_category": "TV",
        "input_source": INPUT_SOURCE_RAW,
        "taxonomy_version": CORE3_M04C_TV_TAXONOMY_VERSION,
        "old_rule_version": "m04c_tv_claim_fact_profile_v0.1",
        "rule_version": CORE3_M04C_TV_RULE_VERSION,
    },
    "AC": {
        "batch_id": "m00_20260624000202_1150a669",
        "product_category": "AC",
        "input_source": INPUT_SOURCE_EVIDENCE,
        "taxonomy_version": CORE3_M04C_AC_TAXONOMY_VERSION,
        "old_rule_version": "m04c_ac_claim_fact_profile_v0.1",
        "rule_version": CORE3_M04C_AC_RULE_VERSION,
    },
}

DOWNSTREAM_TABLES = (
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
        before = {category: capture_db_category(db, category, use_new=False) for category in CATEGORY_CONFIG}
        shadow = {category: capture_shadow_category(db, category) for category in CATEGORY_CONFIG}
        shadow_comparisons = {
            category: compare_category(before[category], shadow[category], category)
            for category in CATEGORY_CONFIG
        }
        assert_shadow_acceptance(shadow_comparisons)
        run_results: dict[str, dict[str, Any]] = {}
        if args.write_draft:
            for category, config in CATEGORY_CONFIG.items():
                result = M04CRunner(db).run_batch(
                    project_id=PROJECT_ID,
                    category_code=category,
                    batch_id=config["batch_id"],
                    product_category=config["product_category"],
                    taxonomy_version=config["taxonomy_version"],
                    rule_version=config["rule_version"],
                    input_source=config["input_source"],
                    force_rebuild=False,
                )
                status = result.status.value if hasattr(result.status, "value") else str(result.status)
                if status not in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value}:
                    db.rollback()
                    raise RuntimeError(f"{category} M04C draft failed: {result.summary_json}")
                db.commit()
                run_results[category] = {
                    "status": status,
                    "input_count": result.input_count,
                    "output_count": result.output_count,
                    "warnings": list(result.warnings),
                    "summary": result.summary_json,
                }
        after = {
            category: capture_db_category(db, category, use_new=True)
            if args.write_draft
            else shadow[category]
            for category in CATEGORY_CONFIG
        }
        downstream_after = capture_downstream_guard(db)

    comparisons = {
        category: compare_category(before[category], after[category], category)
        for category in CATEGORY_CONFIG
    }
    payload = {
        "task_id": "M12D-QF-03",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": "M04C only",
        "write_draft": args.write_draft,
        "allowed_migrations": {
            "TV": [
                "m03b_param_profile_missing 328 -> 0 through current serving scope",
                "claim_text_unmatched profile flag -> row coverage warning",
                "param_unknown support may recover only where M03B v0.2 provides evidence",
            ],
            "AC": [
                "claim_text_unmatched profile flag -> row coverage warning",
                "M03B lineage v0.1 -> v0.2 with unchanged business parameter values",
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
    print(json.dumps({"status": "ok", "comparisons": comparisons, "downstream_unchanged": downstream_before == downstream_after, "output_json": str(output_json), "output_markdown": str(output_markdown)}, ensure_ascii=False))
    return 0


def capture_db_category(db, category: str, *, use_new: bool) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    rule_version = config["rule_version"] if use_new else config["old_rule_version"]
    profiles = list(
        db.execute(
            select(entities.Core3SkuClaimFactProfile)
            .where(entities.Core3SkuClaimFactProfile.project_id == PROJECT_ID)
            .where(entities.Core3SkuClaimFactProfile.category_code == category)
            .where(entities.Core3SkuClaimFactProfile.product_category == config["product_category"])
            .where(entities.Core3SkuClaimFactProfile.batch_id == config["batch_id"])
            .where(entities.Core3SkuClaimFactProfile.taxonomy_version == config["taxonomy_version"])
            .where(entities.Core3SkuClaimFactProfile.rule_version == rule_version)
        ).scalars()
    )
    facts = list(
        db.execute(
            select(entities.Core3SkuClaimFact)
            .where(entities.Core3SkuClaimFact.project_id == PROJECT_ID)
            .where(entities.Core3SkuClaimFact.category_code == category)
            .where(entities.Core3SkuClaimFact.product_category == config["product_category"])
            .where(entities.Core3SkuClaimFact.batch_id == config["batch_id"])
            .where(entities.Core3SkuClaimFact.taxonomy_version == config["taxonomy_version"])
            .where(entities.Core3SkuClaimFact.rule_version == rule_version)
        ).scalars()
    )
    positions = list(
        db.execute(
            select(entities.Core3SkuClaimDimensionPosition)
            .where(entities.Core3SkuClaimDimensionPosition.project_id == PROJECT_ID)
            .where(entities.Core3SkuClaimDimensionPosition.category_code == category)
            .where(entities.Core3SkuClaimDimensionPosition.product_category == config["product_category"])
            .where(entities.Core3SkuClaimDimensionPosition.batch_id == config["batch_id"])
            .where(entities.Core3SkuClaimDimensionPosition.taxonomy_version == config["taxonomy_version"])
            .where(entities.Core3SkuClaimDimensionPosition.rule_version == rule_version)
        ).scalars()
    )
    return build_capture(
        category,
        rule_version,
        [profile_from_entity(row) for row in profiles],
        [fact_from_entity(row) for row in facts],
        [position_from_entity(row) for row in positions],
    )


def capture_shadow_category(db, category: str) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    context = Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    service = M04CService(context)
    taxonomy = M04CTaxonomyLoader().load(config["taxonomy_version"], product_category=config["product_category"])
    records, source_used = service._read_claim_records(
        config["batch_id"],
        taxonomy=taxonomy,
        input_source=config["input_source"],
        target_sku_codes=(),
    )
    param_profiles = service._read_param_profiles(
        config["batch_id"],
        sku_codes=sorted({record.sku_code for record in records}),
        product_category=config["product_category"],
    )
    profiles, facts, positions, _, _ = M04CProfileBuilder(
        project_id=PROJECT_ID,
        category_code=category,
        batch_id=config["batch_id"],
        taxonomy=taxonomy,
        rule_version=config["rule_version"],
        input_source=source_used,
    ).build(records, param_profiles)
    return build_capture(
        category,
        config["rule_version"],
        [profile_from_payload(profile.payload) for profile in profiles],
        [fact_from_payload(fact.payload) for fact in facts],
        [position_from_payload(position.payload) for position in positions],
    )


def build_capture(
    category: str,
    rule_version: str,
    profiles: Sequence[dict[str, Any]],
    facts: Sequence[dict[str, Any]],
    positions: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    profile_map = {str(row["sku_code"]): row for row in profiles}
    fact_map = {fact_key(row): row for row in facts}
    position_map = {position_key(row): row for row in positions}
    quality_flags = Counter(flag for row in profiles for flag in row.get("quality_flags", []))
    support_statuses = Counter(str(row.get("param_support_status")) for row in facts)
    m03b_batches = Counter(str(row.get("m03b_param_profile_batch_id") or "missing") for row in profiles)
    unmatched_rows = sum(int(row.get("unmatched_claim_text_count") or 0) for row in profiles)
    coverage_warning_skus = sum(1 for row in profiles if int(row.get("unmatched_claim_text_count") or 0) > 0)
    return {
        "category": category,
        "rule_version": rule_version,
        "profile_count": len(profiles),
        "fact_count": len(facts),
        "position_count": len(positions),
        "quality_flag_counts": dict(sorted(quality_flags.items())),
        "support_status_counts": dict(sorted(support_statuses.items())),
        "m03b_source_batch_counts": dict(sorted(m03b_batches.items())),
        "unmatched_row_count": unmatched_rows,
        "coverage_warning_sku_count": coverage_warning_skus,
        "profiles": profile_map,
        "facts": fact_map,
        "positions": position_map,
    }


def compare_category(before: dict[str, Any], after: dict[str, Any], category: str) -> dict[str, Any]:
    old_fact_keys = set(before["facts"])
    new_fact_keys = set(after["facts"])
    common_fact_keys = sorted(old_fact_keys & new_fact_keys)
    immutable_fact_changes = [
        key for key in common_fact_keys
        if immutable_fact(before["facts"][key]) != immutable_fact(after["facts"][key])
    ]
    support_migrations = Counter(
        f"{before['facts'][key]['param_support_status']}->{after['facts'][key]['param_support_status']}"
        for key in common_fact_keys
    )
    non_unknown_support_changes = [
        key for key in common_fact_keys
        if before["facts"][key]["param_support_status"] != after["facts"][key]["param_support_status"]
        and before["facts"][key]["param_support_status"] != "param_unknown"
    ]
    claim_kind_changes = [
        key for key in common_fact_keys
        if before["facts"][key].get("claim_kind") != after["facts"][key].get("claim_kind")
    ]
    profile_keys = sorted(set(before["profiles"]) & set(after["profiles"]))
    claim_code_changes = [
        key for key in profile_keys
        if before["profiles"][key]["claim_codes"] != after["profiles"][key]["claim_codes"]
    ]
    claimed_position_changes = [
        key for key in set(before["positions"]) & set(after["positions"])
        if key.endswith(":claimed") and before["positions"][key]["position_code"] != after["positions"][key]["position_code"]
    ]
    support_business_changes = [
        key for key in common_fact_keys
        if support_fact(before["facts"][key]) != support_fact(after["facts"][key])
    ]
    support_core_changes = [
        key for key in common_fact_keys
        if support_core_fact(before["facts"][key]) != support_core_fact(after["facts"][key])
    ]
    regression_pool = [
        key for key in profile_keys
        if "m03b_param_profile_missing" not in before["profiles"][key]["quality_flags"]
    ]
    if not regression_pool:
        regression_pool = profile_keys
    return {
        "common_profile_count": len(profile_keys),
        "missing_profile_count": len(set(before["profiles"]) - set(after["profiles"])),
        "extra_profile_count": len(set(after["profiles"]) - set(before["profiles"])),
        "missing_fact_count": len(old_fact_keys - new_fact_keys),
        "extra_fact_count": len(new_fact_keys - old_fact_keys),
        "immutable_fact_changed_count": len(immutable_fact_changes),
        "preexisting_claim_kind_changed_count": len(claim_kind_changes),
        "claim_code_changed_count": len(claim_code_changes),
        "claimed_position_changed_count": len(claimed_position_changes),
        "support_migration_distribution": dict(sorted(support_migrations.items())),
        "non_unknown_support_changed_count": len(non_unknown_support_changes),
        "support_business_changed_count": len(support_business_changes),
        "support_business_changed_sample": support_business_changes[:20],
        "support_core_changed_count": len(support_core_changes),
        "support_core_changed_sample": support_core_changes[:20],
        "regression_pool_count": len(regression_pool),
        "regression_sample": regression_pool[:20],
    }


def assert_shadow_acceptance(comparisons: Mapping[str, Mapping[str, Any]]) -> None:
    for category, comparison in comparisons.items():
        for field in (
            "missing_profile_count",
            "extra_profile_count",
            "missing_fact_count",
            "extra_fact_count",
            "immutable_fact_changed_count",
            "claim_code_changed_count",
            "claimed_position_changed_count",
        ):
            if int(comparison[field]) != 0:
                raise RuntimeError(f"{category} shadow acceptance failed: {field}={comparison[field]}")
    if int(comparisons["AC"]["support_core_changed_count"]) != 0:
        raise RuntimeError("AC M04C support status or supporting params changed despite equivalent M03B v0.2 inputs")
    if int(comparisons["TV"]["non_unknown_support_changed_count"]) != 0:
        raise RuntimeError("TV M04C changed support that was already known before serving-scope repair")


def profile_from_entity(row: entities.Core3SkuClaimFactProfile) -> dict[str, Any]:
    summary = row.claim_summary_json or {}
    return {
        "sku_code": row.sku_code,
        "claim_codes": sorted(row.claim_codes or []),
        "quality_flags": sorted(row.quality_flags or []),
        "unmatched_claim_text_count": int(summary.get("unmatched_claim_text_count") or 0),
        "m03b_param_profile_batch_id": summary.get("m03b_param_profile_batch_id"),
    }


def profile_from_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    summary = row.get("claim_summary_json") or {}
    return {
        "sku_code": row["sku_code"],
        "claim_codes": sorted(row.get("claim_codes") or []),
        "quality_flags": sorted(row.get("quality_flags") or []),
        "unmatched_claim_text_count": int(summary.get("unmatched_claim_text_count") or 0),
        "m03b_param_profile_batch_id": summary.get("m03b_param_profile_batch_id"),
    }


def fact_from_entity(row: entities.Core3SkuClaimFact) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "source_claim_key": row.source_claim_key,
        "claim_code": row.claim_code,
        "claim_name": row.claim_name,
        "claim_dimension": row.claim_dimension,
        "claim_kind": row.claim_kind,
        "clean_claim_text": row.clean_claim_text,
        "service_separate_flag": row.service_separate_flag,
        "param_support_status": row.param_support_status,
        "param_support_level": row.param_support_level,
        "param_support_specificity": row.param_support_specificity,
        "supporting_param_codes": sorted(row.supporting_param_codes or []),
        "primary_supporting_param_codes": sorted(row.primary_supporting_param_codes or []),
        "generic_support_param_codes": sorted(row.generic_support_param_codes or []),
        "wtp_input_guard": row.wtp_input_guard,
        "fact_claim_flag": row.fact_claim_flag,
        "confidence": str(row.confidence),
    }


def fact_from_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": row["sku_code"],
        "source_claim_key": row["source_claim_key"],
        "claim_code": row["claim_code"],
        "claim_name": row["claim_name"],
        "claim_dimension": row["claim_dimension"],
        "claim_kind": row["claim_kind"],
        "clean_claim_text": row.get("clean_claim_text"),
        "service_separate_flag": bool(row.get("service_separate_flag")),
        "param_support_status": row["param_support_status"],
        "param_support_level": row["param_support_level"],
        "param_support_specificity": row["param_support_specificity"],
        "supporting_param_codes": sorted(row.get("supporting_param_codes") or []),
        "primary_supporting_param_codes": sorted(row.get("primary_supporting_param_codes") or []),
        "generic_support_param_codes": sorted(row.get("generic_support_param_codes") or []),
        "wtp_input_guard": row["wtp_input_guard"],
        "fact_claim_flag": bool(row.get("fact_claim_flag")),
        "confidence": str(row.get("confidence")),
    }


def position_from_entity(row: entities.Core3SkuClaimDimensionPosition) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "dimension_code": row.dimension_code,
        "position_source": row.position_source,
        "position_code": row.position_code,
    }


def position_from_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": row["sku_code"],
        "dimension_code": row["dimension_code"],
        "position_source": row["position_source"],
        "position_code": row["position_code"],
    }


def fact_key(row: Mapping[str, Any]) -> str:
    return f"{row['sku_code']}:{row['source_claim_key']}:{row['claim_code']}"


def position_key(row: Mapping[str, Any]) -> str:
    return f"{row['sku_code']}:{row['dimension_code']}:{row['position_source']}"


def immutable_fact(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("claim_name"),
        row.get("claim_dimension"),
        row.get("clean_claim_text"),
        bool(row.get("service_separate_flag")),
    )


def support_core_fact(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("param_support_status"),
        tuple(row.get("supporting_param_codes") or []),
        bool(row.get("fact_claim_flag")),
    )


def support_fact(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("param_support_status"),
        row.get("param_support_level"),
        row.get("param_support_specificity"),
        tuple(row.get("supporting_param_codes") or []),
        tuple(row.get("primary_supporting_param_codes") or []),
        tuple(row.get("generic_support_param_codes") or []),
        row.get("wtp_input_guard"),
        bool(row.get("fact_claim_flag")),
        str(row.get("confidence")),
    )


def compact_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in capture.items() if key not in {"profiles", "facts", "positions"}}


def capture_downstream_guard(db) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(text(f"SELECT count(*) AS row_count, max(updated_at) AS max_updated_at FROM {table_name}")).mappings().one()
        result[table_name] = {
            "row_count": int(row["row_count"]),
            "max_updated_at": row["max_updated_at"].isoformat() if row["max_updated_at"] else None,
        }
    return result


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-03 M04C TV/AC Draft Rerun Report",
        "",
        f"- Generated at: `{payload['generated_at']}`",
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
                f"- Facts: `{before['fact_count']} -> {after['fact_count']}`",
                f"- Profile flags: `{json.dumps(before['quality_flag_counts'], ensure_ascii=False)} -> {json.dumps(after['quality_flag_counts'], ensure_ascii=False)}`",
                f"- Unmatched rows: `{before['unmatched_row_count']} -> {after['unmatched_row_count']}`",
                f"- Coverage-warning SKUs: `{before['coverage_warning_sku_count']} -> {after['coverage_warning_sku_count']}`",
                f"- M03B source batches: `{json.dumps(after['m03b_source_batch_counts'], ensure_ascii=False)}`",
                f"- Support migrations: `{json.dumps(comparison['support_migration_distribution'], ensure_ascii=False)}`",
                f"- Missing/extra facts: `{comparison['missing_fact_count']}/{comparison['extra_fact_count']}`",
                f"- Immutable fact changes: `{comparison['immutable_fact_changed_count']}`",
                f"- Pre-existing claim-kind drift: `{comparison['preexisting_claim_kind_changed_count']}`",
                f"- Claim-code changes: `{comparison['claim_code_changed_count']}`",
                f"- Claimed-position changes: `{comparison['claimed_position_changed_count']}`",
                f"- Support-core changes: `{comparison['support_core_changed_count']}`",
                f"- Regression pool: `{comparison['regression_pool_count']}`",
                f"- Regression sample: `{', '.join(comparison['regression_sample'])}`",
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
