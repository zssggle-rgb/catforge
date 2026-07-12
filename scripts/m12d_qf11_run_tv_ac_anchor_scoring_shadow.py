#!/usr/bin/env python3
"""Run two-phase TV/AC M12D anchor-scoring shadow without database writes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
)
from app.services.core3_real_data.purchase_reason_anchor_candidate_generator import (
    AnchorCandidateGenerator,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    M12DAnchorTaxonomyLoader,
)
from app.services.core3_real_data.purchase_reason_context_builder import (
    SkuPurchaseReasonContextBuilder,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (
    PurchaseReasonProfileScoringService,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_TAXONOMY = {
    "TV": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    "AC": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
}
DOWNSTREAM_TABLES = (
    "core3_sku_purchase_reason_profile",
    "core3_sku_purchase_reason_anchor",
    "core3_purchase_reason_profile_version",
)
BUSINESS_FIELDS = (
    "role",
    "evidence_strength",
    "confidence",
    "raw_evidence_score",
    "conflict_penalty",
    "adjusted_evidence_score",
    "evidence_domains_json",
    "domain_scores_json",
    "risk_flags_json",
    "downgrade_reason_code",
)
NON_TARGET_FIELDS = (
    "support_summary_cn",
    "source_refs_json",
    "input_fingerprint",
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        guard_before = capture_guard(db)
        snapshot = {
            category: score_category(db, category, limit=args.limit)
            for category in ("TV", "AC")
        }
        guard_after = capture_guard(db)
    if guard_before != guard_after:
        raise RuntimeError("M12D anchor-scoring shadow changed persisted M12D tables")

    payload = {
        "task_id": "M12D-QF-11",
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "categories": snapshot,
        "downstream_guard": {
            "before": guard_before,
            "after": guard_after,
            "unchanged": guard_before == guard_after,
        },
    }
    if args.mode == "compare":
        if not args.baseline_json:
            raise RuntimeError("compare mode requires --baseline-json")
        baseline = json.loads(Path(args.baseline_json).read_text(encoding="utf-8"))
        payload["comparison"] = compare_snapshots(baseline["categories"], snapshot)
        assert_acceptance(payload["comparison"])
        for category_payload in payload["categories"].values():
            category_payload.pop("anchors", None)
            category_payload.pop("sku_anchor_counts", None)
        if not args.output_markdown:
            raise RuntimeError("compare mode requires --output-markdown")
        markdown_path = Path(args.output_markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(payload), encoding="utf-8")

    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "mode": args.mode,
                "categories": {
                    category: {
                        "sku_count": result["sku_count"],
                        "anchor_count": result["anchor_count"],
                    }
                    for category, result in snapshot.items()
                },
                "comparison": (
                    {
                        category: {
                            "business_changed_anchor_count": result[
                                "business_changed_anchor_count"
                            ],
                            "non_target_changed_anchor_count": result[
                                "non_target_changed_anchor_count"
                            ],
                            "new_global_missing_flag_count": result[
                                "new_global_missing_flag_count"
                            ],
                        }
                        for category, result in payload.get("comparison", {}).items()
                    }
                ),
                "downstream_unchanged": guard_before == guard_after,
            },
            ensure_ascii=False,
        )
    )
    return 0


def score_category(db, category: str, *, limit: int) -> dict[str, Any]:
    version = current_published_version(db, category)
    if version is None:
        raise RuntimeError(f"{category} has no current published M12D version")
    profiles = current_profiles(db, category, version.purchase_reason_version_id)
    if limit > 0:
        profiles = profiles[:limit]
    source_batch_ids = tuple(str(item) for item in (version.source_batch_ids_json or ()) if str(item))
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CATEGORY_TAXONOMY[category],
        product_category=category,
    )
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    )
    generator = AnchorCandidateGenerator(taxonomy)
    scorer = PurchaseReasonProfileScoringService()
    anchors: dict[str, dict[str, Any]] = {}
    sku_anchor_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    strength_counts: Counter[str] = Counter()
    risk_flag_counts: Counter[str] = Counter()

    for profile in profiles:
        sku_code = str(profile.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        score_result = scorer.score(candidate_set=candidate_set, context=context)
        for anchor in score_result.scored_anchors:
            key = f"{sku_code}::{anchor.anchor_code}"
            payload = anchor.model_dump(mode="json")
            anchors[key] = payload
            sku_anchor_counts[sku_code] += 1
            role_counts[str(anchor.role)] += 1
            strength_counts[str(anchor.evidence_strength)] += 1
            risk_flag_counts.update(str(flag) for flag in anchor.risk_flags_json)

    return {
        "category": category,
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "source_batch_ids": list(source_batch_ids),
        "read_scope": read_scope,
        "sku_count": len(profiles),
        "anchor_count": len(anchors),
        "sku_anchor_counts": dict(sorted(sku_anchor_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "strength_counts": dict(sorted(strength_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "anchors": anchors,
    }


def compare_snapshots(
    baseline: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result = {}
    for category in ("TV", "AC"):
        before = baseline[category]
        after = current[category]
        before_anchors = before["anchors"]
        after_anchors = after["anchors"]
        added = sorted(set(after_anchors) - set(before_anchors))
        removed = sorted(set(before_anchors) - set(after_anchors))
        business_changes: list[dict[str, Any]] = []
        non_target_changes: list[dict[str, Any]] = []
        role_migrations: Counter[str] = Counter()
        strength_migrations: Counter[str] = Counter()
        applied_issue_counts: Counter[str] = Counter()
        info_effect_violations: list[str] = []
        blocking_core_violations: list[str] = []
        global_missing_removed = 0
        new_global_missing = 0
        unaffected_samples: list[dict[str, Any]] = []
        sampled_skus: set[str] = set()

        for key in sorted(set(before_anchors) & set(after_anchors)):
            old = before_anchors[key]
            new = after_anchors[key]
            changed_business_fields = [
                field for field in BUSINESS_FIELDS if _normalized(old.get(field)) != _normalized(new.get(field))
            ]
            changed_non_target_fields = [
                field
                for field in NON_TARGET_FIELDS
                if _normalized(old.get(field)) != _normalized(new.get(field))
            ]
            if changed_business_fields:
                business_changes.append(
                    {
                        "anchor_key": key,
                        "changed_fields": changed_business_fields,
                        "old": {field: old.get(field) for field in changed_business_fields},
                        "new": {field: new.get(field) for field in changed_business_fields},
                    }
                )
            if changed_non_target_fields:
                non_target_changes.append(
                    {"anchor_key": key, "changed_fields": changed_non_target_fields}
                )
            role_migrations[f"{old.get('role')}->{new.get('role')}"] += 1
            strength_migrations[
                f"{old.get('evidence_strength')}->{new.get('evidence_strength')}"
            ] += 1
            old_flags = {str(flag) for flag in old.get("risk_flags_json") or ()}
            new_flags = {str(flag) for flag in new.get("risk_flags_json") or ()}
            if "missing_or_partial_inputs" in old_flags and "missing_or_partial_inputs" not in new_flags:
                global_missing_removed += 1
            if "missing_or_partial_inputs" in new_flags:
                new_global_missing += 1

            applied_issues = new.get("role_reason_json", {}).get("applied_quality_issues") or []
            has_blocking = False
            for issue in applied_issues:
                if issue.get("applied"):
                    applied_issue_counts[str(issue.get("issue_code"))] += 1
                if issue.get("severity") == "info" and issue.get("applied"):
                    info_effect_violations.append(key)
                if issue.get("severity") == "blocking" and issue.get("applied"):
                    has_blocking = True
            if has_blocking and new.get("role") == "core_payment":
                blocking_core_violations.append(key)
            sku_code = key.split("::", 1)[0]
            if (
                not changed_non_target_fields
                and sku_code not in sampled_skus
                and len(unaffected_samples) < 20
            ):
                sampled_skus.add(sku_code)
                unaffected_samples.append(
                    {
                        "anchor_key": key,
                        "business_changed": bool(changed_business_fields),
                        "non_target_fields_unchanged": True,
                        "source_ref_count": len(new.get("source_refs_json") or ()),
                        "input_fingerprint": new.get("input_fingerprint"),
                    }
                )

        affected_skus = sorted(
            {change["anchor_key"].split("::", 1)[0] for change in business_changes}
        )
        result[category] = {
            "sku_count": after["sku_count"],
            "before_anchor_count": before["anchor_count"],
            "after_anchor_count": after["anchor_count"],
            "added_anchor_count": len(added),
            "removed_anchor_count": len(removed),
            "added_anchor_keys": added,
            "removed_anchor_keys": removed,
            "business_changed_anchor_count": len(business_changes),
            "business_changed_anchor_keys": [
                change["anchor_key"] for change in business_changes
            ],
            "business_change_samples": business_changes[:100],
            "affected_sku_count": len(affected_skus),
            "affected_skus": affected_skus,
            "non_target_changed_anchor_count": len(non_target_changes),
            "non_target_changes": non_target_changes,
            "role_migrations": dict(sorted(role_migrations.items())),
            "strength_migrations": dict(sorted(strength_migrations.items())),
            "before_role_counts": before["role_counts"],
            "after_role_counts": after["role_counts"],
            "before_strength_counts": before["strength_counts"],
            "after_strength_counts": after["strength_counts"],
            "before_risk_flag_counts": before["risk_flag_counts"],
            "after_risk_flag_counts": after["risk_flag_counts"],
            "global_missing_flag_removed_count": global_missing_removed,
            "new_global_missing_flag_count": new_global_missing,
            "applied_issue_counts": dict(sorted(applied_issue_counts.items())),
            "info_effect_violation_count": len(set(info_effect_violations)),
            "blocking_core_violation_count": len(set(blocking_core_violations)),
            "unaffected_non_target_samples": unaffected_samples,
        }
    return result


def assert_acceptance(comparison: Mapping[str, Mapping[str, Any]]) -> None:
    for category, result in comparison.items():
        if result["added_anchor_count"] or result["removed_anchor_count"]:
            raise RuntimeError(f"{category} candidate anchor set changed during scoring-only shadow")
        if result["non_target_changed_anchor_count"]:
            raise RuntimeError(f"{category} non-target anchor fields changed")
        if result["new_global_missing_flag_count"]:
            raise RuntimeError(f"{category} still emits missing_or_partial_inputs on anchors")
        if result["info_effect_violation_count"]:
            raise RuntimeError(f"{category} info issue affected anchor scoring")
        if result["blocking_core_violation_count"]:
            raise RuntimeError(f"{category} blocking issue became core")
        if len(result["unaffected_non_target_samples"]) < min(20, int(result["sku_count"])):
            raise RuntimeError(f"{category} has fewer than 20 non-target regression samples")


def current_published_version(db, category: str) -> Any:
    return db.scalars(
        select(entities.Core3PurchaseReasonProfileVersion)
        .where(entities.Core3PurchaseReasonProfileVersion.project_id == PROJECT_ID)
        .where(entities.Core3PurchaseReasonProfileVersion.category_code == category)
        .where(entities.Core3PurchaseReasonProfileVersion.product_category == category)
        .where(entities.Core3PurchaseReasonProfileVersion.release_status == "published")
        .where(entities.Core3PurchaseReasonProfileVersion.is_current.is_(True))
        .order_by(entities.Core3PurchaseReasonProfileVersion.published_at.desc())
    ).first()


def current_profiles(db, category: str, version_id: str) -> list[Any]:
    return list(
        db.scalars(
            select(entities.Core3SkuPurchaseReasonProfile)
            .where(entities.Core3SkuPurchaseReasonProfile.project_id == PROJECT_ID)
            .where(entities.Core3SkuPurchaseReasonProfile.category_code == category)
            .where(entities.Core3SkuPurchaseReasonProfile.product_category == category)
            .where(entities.Core3SkuPurchaseReasonProfile.purchase_reason_version_id == version_id)
            .where(entities.Core3SkuPurchaseReasonProfile.is_current.is_(True))
            .order_by(entities.Core3SkuPurchaseReasonProfile.sku_code)
        )
    )


def capture_guard(db) -> dict[str, dict[str, Any]]:
    result = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table_name}")
        ).one()
        result[table_name] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-11 TV/AC Anchor Scoring Shadow",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 范围：只比较锚点评分、置信度和角色；不写画像、状态、复核或发布结果。",
        "",
        "| 品类 | SKU | 锚点 | 评分业务字段变化 | 非目标字段变化 | 移除全局 missing 风险 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in ("TV", "AC"):
        result = payload["comparison"][category]
        lines.append(
            f"| {category} | {result['sku_count']} | {result['after_anchor_count']} | "
            f"{result['business_changed_anchor_count']} | "
            f"{result['non_target_changed_anchor_count']} | "
            f"{result['global_missing_flag_removed_count']} |"
        )
    for category in ("TV", "AC"):
        result = payload["comparison"][category]
        lines.extend(
            [
                "",
                f"## {category}",
                "",
                f"- 角色迁移：`{result['role_migrations']}`",
                f"- 强度迁移：`{result['strength_migrations']}`",
                f"- 应用的 scoped issue：`{result['applied_issue_counts']}`",
                f"- 新全局 missing 风险：`{result['new_global_missing_flag_count']}`",
                f"- info 误影响：`{result['info_effect_violation_count']}`",
                f"- blocking 成为 core：`{result['blocking_core_violation_count']}`",
                f"- 非目标字段回归样本：`{len(result['unaffected_non_target_samples'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            f"- M12D 持久化表未变化：`{payload['downstream_guard']['unchanged']}`",
            "- 候选锚点集合、source refs、支持摘要和 input fingerprint 不变；评分域可因剔除无关 M12C 而变化。",
            "- `missing_or_partial_inputs` 不再进入锚点风险、分数或置信度。",
            "- TV/AC 使用各自 taxonomy；本任务未写 current/published。",
            "",
        ]
    )
    return "\n".join(lines)


def _normalized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("snapshot", "compare"), required=True)
    parser.add_argument("--baseline-json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
