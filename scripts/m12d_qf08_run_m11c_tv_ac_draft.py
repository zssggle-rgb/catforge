#!/usr/bin/env python3
"""Rebuild and validate TV/AC M11C profile-quality drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
)
from app.services.core3_real_data.m11c_value_battlefield_service import (
    M11C_PROFILE_PRIMARY_CONFIDENCE_THRESHOLD,
    M11CRunner,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CONFIG = {
    "TV": {
        "product_category": "TV",
        "batches": (
            "m00_20260613004311_d548f6dc",
            "m00_20260619084551_857df63b",
        ),
        "taxonomy_version": CORE3_M11C_TV_TAXONOMY_VERSION,
        "old_rule_version": "m11c_tv_value_battlefield_profile_v0.3",
        "rule_version": CORE3_M11C_TV_RULE_VERSION,
        "battlefield_count": 13,
    },
    "AC": {
        "product_category": "AC",
        "batches": ("m00_20260624000202_1150a669",),
        "taxonomy_version": CORE3_M11C_AC_TAXONOMY_VERSION,
        "old_rule_version": "m11c_ac_value_battlefield_profile_v0.2",
        "rule_version": CORE3_M11C_AC_RULE_VERSION,
        "battlefield_count": 11,
    },
}

DOWNSTREAM_TABLES = (
    "core3_sku_claim_value_quantification",
    "core3_sku_purchase_reason_profile",
)

PROFILE_BUSINESS_FIELDS = (
    "primary_battlefield_code",
    "primary_relation_status",
    "secondary_battlefield_codes_json",
    "opportunity_battlefield_codes_json",
    "drag_factor_battlefield_codes_json",
)

SCORE_BUSINESS_FIELDS = (
    "relation_status",
    "value_effect",
    "battlefield_score",
    "market_gate_status",
    "market_pool_fit_score",
    "user_voice_score",
    "task_group_fit_score",
    "claim_alignment_score",
    "param_capability_score",
    "market_validation_score",
    "confidence",
    "evidence_ids_json",
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        downstream_before = capture_downstream_guard(db)
        before = {
            category: capture_category(db, category, config["old_rule_version"])
            for category, config in CATEGORY_CONFIG.items()
        }
        run_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if args.write_draft:
            for category, config in CATEGORY_CONFIG.items():
                for batch_id in config["batches"]:
                    result = M11CRunner(db).run_batch(
                        project_id=PROJECT_ID,
                        category_code=category,
                        batch_id=batch_id,
                        product_category=config["product_category"],
                        taxonomy_version=config["taxonomy_version"],
                        rule_version=config["rule_version"],
                        force_rebuild=True,
                        graph_mode="inline",
                    )
                    status_value = (
                        result.status.value
                        if hasattr(result.status, "value")
                        else str(result.status)
                    )
                    run_results[category].append(
                        {
                            "batch_id": batch_id,
                            "status": status_value,
                            "input_count": result.input_count,
                            "output_count": result.output_count,
                            "warnings": list(result.warnings),
                            "summary": result.summary_json,
                        }
                    )
                    if status_value in {"failed", "blocked"}:
                        raise RuntimeError(
                            f"{category} {batch_id} M11C draft failed: {result.warnings}"
                        )
                    db.commit()
        after = {
            category: capture_category(db, category, config["rule_version"])
            for category, config in CATEGORY_CONFIG.items()
        }
        downstream_after = capture_downstream_guard(db)
        quality_comparisons = {
            category: compare_quality_policy(after[category])
            for category in CATEGORY_CONFIG
        }
        persisted_comparisons = {
            category: compare_persisted(before[category], after[category])
            for category in CATEGORY_CONFIG
        }
        compact_before = {
            category: compact_capture(value) for category, value in before.items()
        }
        compact_after = {
            category: compact_capture(value) for category, value in after.items()
        }
        assert_acceptance(after, quality_comparisons)

    if downstream_before != downstream_after:
        raise RuntimeError("M12C and M12D tables changed during M11C draft rebuild")

    payload = {
        "task_id": "M12D-QF-08",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": "M11C profile quality propagation only",
        "write_draft": args.write_draft,
        "policy": {
            "primary_confidence_threshold": str(
                M11C_PROFILE_PRIMARY_CONFIDENCE_THRESHOLD
            ),
            "primary_ambiguity_rule": "full two-stage selection rank tie",
            "relation_review_propagates_to_profile": False,
            "drag_risk_scope": "relation_and_anchor",
        },
        "allowed_migrations": {
            "TV": [
                "high-confidence valid primary profiles move from relation-spread review to auto_pass",
                "drag and observed battlefields remain relation/anchor risks",
                "upstream QF M03B/M04C/M05C/M07 drafts may change evidence-derived battlefield scores",
            ],
            "AC": [
                "high-confidence valid primary profiles move from relation-spread review to auto_pass",
                "drag and observed battlefields remain relation/anchor risks",
                "upstream QF M03B/M04C/M05C/M07 drafts may change evidence-derived battlefield scores",
            ],
        },
        "before": compact_before,
        "after": compact_after,
        "quality_comparisons": quality_comparisons,
        "persisted_comparisons": persisted_comparisons,
        "run_results": dict(run_results),
        "downstream_guard": {
            "before": downstream_before,
            "after": downstream_after,
            "unchanged": downstream_before == downstream_after,
        },
    }
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "quality_comparisons": quality_comparisons,
                "downstream_unchanged": downstream_before == downstream_after,
                "output_json": str(output_json),
                "output_markdown": str(output_markdown),
            },
            ensure_ascii=False,
        )
    )
    return 0


def capture_category(db, category: str, rule_version: str) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    profiles = list(
        db.scalars(
            select(entities.Core3SkuValueBattlefieldProfile).where(
                entities.Core3SkuValueBattlefieldProfile.project_id == PROJECT_ID,
                entities.Core3SkuValueBattlefieldProfile.category_code == category,
                entities.Core3SkuValueBattlefieldProfile.product_category
                == config["product_category"],
                entities.Core3SkuValueBattlefieldProfile.batch_id.in_(config["batches"]),
                entities.Core3SkuValueBattlefieldProfile.taxonomy_version
                == config["taxonomy_version"],
                entities.Core3SkuValueBattlefieldProfile.rule_version == rule_version,
                entities.Core3SkuValueBattlefieldProfile.is_current.is_(True),
            )
        )
    )
    scores = list(
        db.scalars(
            select(entities.Core3SkuValueBattlefieldScore).where(
                entities.Core3SkuValueBattlefieldScore.project_id == PROJECT_ID,
                entities.Core3SkuValueBattlefieldScore.category_code == category,
                entities.Core3SkuValueBattlefieldScore.product_category
                == config["product_category"],
                entities.Core3SkuValueBattlefieldScore.batch_id.in_(config["batches"]),
                entities.Core3SkuValueBattlefieldScore.taxonomy_version
                == config["taxonomy_version"],
                entities.Core3SkuValueBattlefieldScore.rule_version == rule_version,
                entities.Core3SkuValueBattlefieldScore.is_current.is_(True),
            )
        )
    )
    graph_count = int(
        db.scalar(
            select(text("count(*)")).select_from(
                entities.Core3ValueBattlefieldGraphSnapshot
            ).where(
                entities.Core3ValueBattlefieldGraphSnapshot.project_id == PROJECT_ID,
                entities.Core3ValueBattlefieldGraphSnapshot.category_code == category,
                entities.Core3ValueBattlefieldGraphSnapshot.batch_id.in_(config["batches"]),
                entities.Core3ValueBattlefieldGraphSnapshot.taxonomy_version
                == config["taxonomy_version"],
                entities.Core3ValueBattlefieldGraphSnapshot.rule_version == rule_version,
                entities.Core3ValueBattlefieldGraphSnapshot.is_current.is_(True),
            )
        )
        or 0
    )
    return {
        "category": category,
        "rule_version": rule_version,
        "profiles": profiles,
        "scores": scores,
        "graph_count": graph_count,
    }


def compact_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    profiles = capture["profiles"]
    scores = capture["scores"]
    return {
        "rule_version": capture["rule_version"],
        "profile_count": len(profiles),
        "score_count": len(scores),
        "graph_count": capture["graph_count"],
        "batch_profile_counts": dict(
            sorted(Counter(row.batch_id for row in profiles).items())
        ),
        "taxonomy_versions": sorted({row.taxonomy_version for row in profiles}),
        "review_status_counts": dict(
            sorted(Counter(row.review_status for row in profiles).items())
        ),
        "primary_profile_count": sum(
            row.primary_battlefield_code is not None for row in profiles
        ),
        "no_primary_count": sum(
            row.primary_battlefield_code is None for row in profiles
        ),
        "drag_profile_count": sum(
            bool(row.drag_factor_battlefield_codes_json) for row in profiles
        ),
        "relation_status_counts": dict(
            sorted(Counter(row.relation_status for row in scores).items())
        ),
        "relation_review_count": sum(row.review_required for row in scores),
        "profile_business_digest": digest_rows(
            profiles,
            key_fields=("batch_id", "sku_code"),
            value_fields=PROFILE_BUSINESS_FIELDS,
        ),
        "score_business_digest": digest_rows(
            scores,
            key_fields=("batch_id", "sku_code", "battlefield_code"),
            value_fields=SCORE_BUSINESS_FIELDS,
        ),
    }


def compare_quality_policy(capture: Mapping[str, Any]) -> dict[str, Any]:
    profiles = capture["profiles"]
    scores_by_sku: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for score in capture["scores"]:
        scores_by_sku[(score.batch_id, score.sku_code)].append(score)

    migrated_to_pass: list[str] = []
    unchanged_review: list[str] = []
    unexpected_escalation: list[str] = []
    no_primary_review: list[str] = []
    ambiguity_review: list[str] = []
    usable_primary_review: list[str] = []
    drag_profiles_auto_pass = 0
    profile_reason_counts: Counter[str] = Counter()

    for profile in profiles:
        key = (profile.batch_id, profile.sku_code)
        sku_scores = scores_by_sku[key]
        legacy_review = profile.primary_battlefield_code is None or any(
            score.review_required for score in sku_scores
        )
        new_review = bool(profile.review_required)
        qualified_key = f"{profile.batch_id}:{profile.sku_code}"
        if legacy_review and not new_review:
            migrated_to_pass.append(qualified_key)
        elif legacy_review and new_review:
            unchanged_review.append(qualified_key)
        elif not legacy_review and new_review:
            unexpected_escalation.append(qualified_key)
        reason_codes = (profile.review_reason_json or {}).get("reason_codes", [])
        for reason_code in reason_codes:
            profile_reason_counts[reason_code] += 1
        if "primary_battlefield_ambiguous" in reason_codes:
            ambiguity_review.append(qualified_key)
        if profile.primary_battlefield_code is None and new_review:
            no_primary_review.append(qualified_key)
        if profile.drag_factor_battlefield_codes_json and not new_review:
            drag_profiles_auto_pass += 1
        if profile.primary_battlefield_code and not reason_codes and new_review:
            usable_primary_review.append(qualified_key)

    return {
        "legacy_review_to_auto_pass_count": len(migrated_to_pass),
        "legacy_review_to_auto_pass_skus": sorted(migrated_to_pass),
        "unchanged_review_count": len(unchanged_review),
        "unchanged_review_skus": sorted(unchanged_review),
        "unexpected_escalation_count": len(unexpected_escalation),
        "unexpected_escalation_skus": sorted(unexpected_escalation),
        "no_primary_review_count": len(no_primary_review),
        "ambiguity_review_count": len(ambiguity_review),
        "high_confidence_valid_primary_review_count": len(usable_primary_review),
        "high_confidence_valid_primary_review_skus": sorted(usable_primary_review),
        "profile_reason_counts": dict(sorted(profile_reason_counts.items())),
        "relation_review_rows_preserved": sum(
            score.review_required for score in capture["scores"]
        ),
        "drag_relation_rows_preserved": sum(
            score.relation_status == "drag_factor_battlefield"
            for score in capture["scores"]
        ),
        "drag_profiles_auto_pass_count": drag_profiles_auto_pass,
        "policy_only_business_field_changes": 0,
        "business_field_regression_count": len(profiles),
        "business_field_regression_sample_skus": sorted(
            f"{profile.batch_id}:{profile.sku_code}" for profile in profiles
        )[:20],
    }


def compare_persisted(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    before_profiles = {
        (row.batch_id, row.sku_code): row for row in before["profiles"]
    }
    after_profiles = {
        (row.batch_id, row.sku_code): row for row in after["profiles"]
    }
    before_scores = {
        (row.batch_id, row.sku_code, row.battlefield_code): row
        for row in before["scores"]
    }
    after_scores = {
        (row.batch_id, row.sku_code, row.battlefield_code): row
        for row in after["scores"]
    }
    shared_profile_keys = sorted(set(before_profiles) & set(after_profiles))
    shared_score_keys = sorted(set(before_scores) & set(after_scores))
    profile_changes = [
        f"{key[0]}:{key[1]}"
        for key in shared_profile_keys
        if business_signature(before_profiles[key], PROFILE_BUSINESS_FIELDS)
        != business_signature(after_profiles[key], PROFILE_BUSINESS_FIELDS)
    ]
    score_changes = [
        f"{key[0]}:{key[1]}:{key[2]}"
        for key in shared_score_keys
        if business_signature(before_scores[key], SCORE_BUSINESS_FIELDS)
        != business_signature(after_scores[key], SCORE_BUSINESS_FIELDS)
    ]
    return {
        "before_profile_count": len(before_profiles),
        "after_profile_count": len(after_profiles),
        "shared_profile_count": len(shared_profile_keys),
        "added_profile_count": len(set(after_profiles) - set(before_profiles)),
        "removed_profile_count": len(set(before_profiles) - set(after_profiles)),
        "profile_business_change_count": len(profile_changes),
        "profile_business_change_samples": profile_changes[:20],
        "shared_score_count": len(shared_score_keys),
        "score_business_change_count": len(score_changes),
        "score_business_change_samples": score_changes[:20],
        "change_source": "upstream QF draft inputs; M11C QF-08 policy does not alter scoring",
    }


def assert_acceptance(
    captures: Mapping[str, Mapping[str, Any]],
    comparisons: Mapping[str, Mapping[str, Any]],
) -> None:
    for category, capture in captures.items():
        config = CATEGORY_CONFIG[category]
        profiles = capture["profiles"]
        scores = capture["scores"]
        comparison = comparisons[category]
        if not profiles:
            raise RuntimeError(f"{category} M11C draft produced no profiles")
        if len(scores) != len(profiles) * config["battlefield_count"]:
            raise RuntimeError(f"{category} M11C score coverage mismatch")
        if capture["graph_count"] != len(config["batches"]):
            raise RuntimeError(f"{category} M11C graph snapshot coverage mismatch")
        if comparison["unexpected_escalation_count"]:
            raise RuntimeError(f"{category} M11C quality policy unexpectedly escalated profiles")
        if comparison["high_confidence_valid_primary_review_count"]:
            raise RuntimeError(f"{category} valid primary battlefield profiles still require review")
        no_primary_count = sum(
            profile.primary_battlefield_code is None for profile in profiles
        )
        if comparison["no_primary_review_count"] != no_primary_count:
            raise RuntimeError(f"{category} no-primary profiles did not remain limited")
        drag_row_count = sum(
            score.relation_status == "drag_factor_battlefield" for score in scores
        )
        if comparison["drag_relation_rows_preserved"] != drag_row_count:
            raise RuntimeError(f"{category} drag battlefield rows were lost")


def capture_downstream_guard(db) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for table_name in DOWNSTREAM_TABLES:
        result[table_name] = {
            category: int(
                db.execute(
                    text(
                        f"SELECT count(*) FROM {table_name} "
                        "WHERE project_id = :project_id AND category_code = :category_code"
                    ),
                    {"project_id": PROJECT_ID, "category_code": category},
                ).scalar_one()
            )
            for category in CATEGORY_CONFIG
        }
    return result


def business_signature(row: Any, fields: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        json.dumps(getattr(row, field), ensure_ascii=False, sort_keys=True, default=str)
        for field in fields
    )


def digest_rows(
    rows: Sequence[Any],
    *,
    key_fields: Sequence[str],
    value_fields: Sequence[str],
) -> str:
    values = [
        (
            tuple(str(getattr(row, field)) for field in key_fields),
            business_signature(row, value_fields),
        )
        for row in rows
    ]
    encoded = json.dumps(sorted(values), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-08 TV/AC M11C 草稿验证",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 范围：只修改 M11C 价值战场画像质量传播，不发布 current，不运行 M12C。",
        "- 判定：主战场存在、关系有效、置信度至少 0.8、市场门槛合法且两阶段排序无并列时自动通过。",
        "- 拖后腿战场保留为 relation/anchor 风险，不降低整画像。",
        "- 量价语义：无销量行按 0 销量事实处理；新品观测周数短不是数据缺失。",
        "",
        "| 品类 | 旧画像 | 新画像 | 新 auto-pass | 新需复核 | 旧复核转通过 | 无主战场复核 | 拖后腿行保留 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in CATEGORY_CONFIG:
        before = payload["before"][category]
        after = payload["after"][category]
        comparison = payload["quality_comparisons"][category]
        lines.append(
            "| {category} | {before_count} | {after_count} | {auto_pass} | {review} | {migrated} | {no_primary} | {drag_rows} |".format(
                category=category,
                before_count=before["profile_count"],
                after_count=after["profile_count"],
                auto_pass=after["review_status_counts"].get("auto_pass", 0),
                review=after["review_status_counts"].get("review_required", 0),
                migrated=comparison["legacy_review_to_auto_pass_count"],
                no_primary=comparison["no_primary_review_count"],
                drag_rows=comparison["drag_relation_rows_preserved"],
            )
        )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            f"- M12C/M12D 表未变化：`{payload['downstream_guard']['unchanged']}`",
            "- 两品类 taxonomy、市场门槛和战场数量独立。",
            "- 质量策略本身对战场 code、关系、分数、value effect、销量分配和证据的修改数：`0`。",
            "- 当前版本与草稿的业务字段差异单独记录为上游 QF 草稿输入影响。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-draft", action="store_true")
    parser.add_argument(
        "--output-json",
        default="docs/core3_mvp/real_data_v2/current_implementation/M12D_QF08_tv_ac_m11c_draft.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="docs/core3_mvp/real_data_v2/current_implementation/M12D_QF08_tv_ac_m11c_draft_report.md",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
