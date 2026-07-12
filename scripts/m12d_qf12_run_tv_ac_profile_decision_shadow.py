#!/usr/bin/env python3
"""Run two-phase TV/AC M12D profile-decision shadow without database writes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
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
VALID_PROFILE_STATUSES = {
    "ready",
    "ready_limited",
    "weak_expression_only",
    "missing_input",
    "failed",
}
ANCHOR_NON_TARGET_FIELDS = (
    "evidence_strength",
    "confidence",
    "raw_evidence_score",
    "conflict_penalty",
    "adjusted_evidence_score",
    "evidence_domains_json",
    "domain_scores_json",
    "support_summary_cn",
    "weakness_summary_cn",
    "source_refs_json",
    "risk_flags_json",
    "input_fingerprint",
)
REVIEW_REASON_CODES = {
    "profile_blocking_issue",
    "release_blocking_issue",
    "core_candidate_blocked_by_input_issue",
}


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        guard_before = capture_guard(db)
        categories = {
            category: score_category(db, category, limit=args.limit)
            for category in ("TV", "AC")
        }
        guard_after = capture_guard(db)
    if guard_before != guard_after:
        raise RuntimeError("M12D profile-decision shadow changed persisted M12D tables")

    payload: dict[str, Any] = {
        "task_id": "M12D-QF-12",
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "categories": categories,
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
        payload["comparison"] = compare_snapshots(baseline["categories"], categories)
        assert_acceptance(payload["comparison"])
        for category_payload in payload["categories"].values():
            category_payload.pop("profiles", None)
            category_payload.pop("anchors", None)
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
                        "status_counts": result["status_counts"],
                        "review_required_count": result["review_required_count"],
                        "core_count_distribution": result["core_count_distribution"],
                    }
                    for category, result in categories.items()
                },
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
    rows = current_profiles(db, category, version.purchase_reason_version_id)
    if limit > 0:
        rows = rows[:limit]
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
    profiles: dict[str, dict[str, Any]] = {}
    anchors: dict[str, dict[str, Any]] = {}
    status_counts: Counter[str] = Counter()
    review_reason_counts: Counter[str] = Counter()
    core_count_distribution: Counter[str] = Counter()

    for row in rows:
        sku_code = str(row.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        score_result = scorer.score(candidate_set=candidate_set, context=context)
        status = str(score_result.status)
        review_reasons = list((score_result.review_reason_json or {}).get("reasons") or ())
        profile = {
            "sku_code": sku_code,
            "status": status,
            "profile_confidence": str(score_result.profile_confidence),
            "confidence_level": str(score_result.confidence_level),
            "core_payment_anchors_json": list(score_result.core_payment_anchors_json),
            "supporting_anchors_json": list(score_result.supporting_anchors_json),
            "weak_expression_anchors_json": list(score_result.weak_expression_anchors_json),
            "risk_drag_anchors_json": list(score_result.risk_drag_anchors_json),
            "review_required": bool(score_result.review_required),
            "review_reason_json": score_result.review_reason_json,
            "confidence_basis_json": getattr(score_result, "confidence_basis_json", {}),
            "input_fingerprint": score_result.input_fingerprint,
        }
        profiles[sku_code] = profile
        status_counts[status] += 1
        core_count_distribution[str(len(profile["core_payment_anchors_json"]))] += 1
        review_reason_counts.update(str(reason) for reason in review_reasons)
        for anchor in score_result.scored_anchors:
            anchors[f"{sku_code}::{anchor.anchor_code}"] = anchor.model_dump(mode="json")

    return {
        "category": category,
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "source_batch_ids": list(source_batch_ids),
        "read_scope": read_scope,
        "sku_count": len(profiles),
        "anchor_count": len(anchors),
        "status_counts": dict(sorted(status_counts.items())),
        "review_required_count": sum(
            1 for profile in profiles.values() if profile["review_required"]
        ),
        "review_reason_counts": dict(sorted(review_reason_counts.items())),
        "core_count_distribution": dict(sorted(core_count_distribution.items())),
        "profiles": profiles,
        "anchors": anchors,
    }


def compare_snapshots(
    baseline: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for category in ("TV", "AC"):
        before = baseline[category]
        after = current[category]
        before_profiles = before["profiles"]
        after_profiles = after["profiles"]
        before_anchors = before["anchors"]
        after_anchors = after["anchors"]
        profile_added = sorted(set(after_profiles) - set(before_profiles))
        profile_removed = sorted(set(before_profiles) - set(after_profiles))
        anchor_added = sorted(set(after_anchors) - set(before_anchors))
        anchor_removed = sorted(set(before_anchors) - set(after_anchors))
        status_migrations: Counter[str] = Counter()
        review_migrations: Counter[str] = Counter()
        affected_skus: list[str] = []
        anchor_role_migrations: Counter[str] = Counter()
        non_target_changes: list[dict[str, Any]] = []
        invalid_status_skus: list[str] = []
        core_limit_violations: list[str] = []
        core_family_violations: list[str] = []
        confidence_formula_violations: list[str] = []
        review_gate_violations: list[str] = []
        unaffected_samples: list[dict[str, Any]] = []

        for sku_code in sorted(set(before_profiles) & set(after_profiles)):
            old = before_profiles[sku_code]
            new = after_profiles[sku_code]
            status_migrations[f"{old['status']}->{new['status']}"] += 1
            review_migrations[
                f"{str(old['review_required']).lower()}->{str(new['review_required']).lower()}"
            ] += 1
            if _normalized(old) != _normalized(new):
                affected_skus.append(sku_code)
            if new["status"] not in VALID_PROFILE_STATUSES:
                invalid_status_skus.append(sku_code)
            core_codes = list(new["core_payment_anchors_json"])
            if len(core_codes) > 3:
                core_limit_violations.append(sku_code)
            families = [
                after_anchors[f"{sku_code}::{code}"].get("anchor_family_code") or code
                for code in core_codes
            ]
            if len(families) != len(set(families)):
                core_family_violations.append(sku_code)
            if not _confidence_matches_core(new, after_anchors):
                confidence_formula_violations.append(sku_code)
            if not _review_gate_valid(new):
                review_gate_violations.append(sku_code)

        for key in sorted(set(before_anchors) & set(after_anchors)):
            old = before_anchors[key]
            new = after_anchors[key]
            anchor_role_migrations[f"{old.get('role')}->{new.get('role')}"] += 1
            changed_fields = [
                field
                for field in ANCHOR_NON_TARGET_FIELDS
                if _normalized(old.get(field)) != _normalized(new.get(field))
            ]
            if changed_fields:
                non_target_changes.append({"anchor_key": key, "changed_fields": changed_fields})

        for sku_code in sorted(after_profiles):
            if len(unaffected_samples) >= min(20, int(after["sku_count"])):
                break
            sku_anchor_keys = sorted(
                key for key in after_anchors if key.startswith(f"{sku_code}::")
            )
            if all(
                all(
                    _normalized(before_anchors[key].get(field))
                    == _normalized(after_anchors[key].get(field))
                    for field in ANCHOR_NON_TARGET_FIELDS
                )
                for key in sku_anchor_keys
            ):
                unaffected_samples.append(
                    {
                        "sku_code": sku_code,
                        "anchor_count": len(sku_anchor_keys),
                        "non_target_anchor_fields_unchanged": True,
                        "profile_changed": sku_code in affected_skus,
                    }
                )

        comparison[category] = {
            "sku_count": after["sku_count"],
            "anchor_count": after["anchor_count"],
            "profile_added_count": len(profile_added),
            "profile_removed_count": len(profile_removed),
            "anchor_added_count": len(anchor_added),
            "anchor_removed_count": len(anchor_removed),
            "affected_sku_count": len(affected_skus),
            "affected_skus": affected_skus,
            "before_status_counts": before["status_counts"],
            "after_status_counts": after["status_counts"],
            "status_migrations": dict(sorted(status_migrations.items())),
            "before_review_required_count": before["review_required_count"],
            "after_review_required_count": after["review_required_count"],
            "review_migrations": dict(sorted(review_migrations.items())),
            "before_review_reason_counts": before["review_reason_counts"],
            "after_review_reason_counts": after["review_reason_counts"],
            "before_core_count_distribution": before["core_count_distribution"],
            "after_core_count_distribution": after["core_count_distribution"],
            "anchor_role_migrations": dict(sorted(anchor_role_migrations.items())),
            "non_target_changed_anchor_count": len(non_target_changes),
            "non_target_changes": non_target_changes,
            "invalid_status_count": len(invalid_status_skus),
            "core_limit_violation_count": len(core_limit_violations),
            "core_family_violation_count": len(core_family_violations),
            "confidence_formula_violation_count": len(confidence_formula_violations),
            "review_gate_violation_count": len(review_gate_violations),
            "unaffected_non_target_samples": unaffected_samples,
        }
    return comparison


def _confidence_matches_core(
    profile: Mapping[str, Any],
    anchors: Mapping[str, Mapping[str, Any]],
) -> bool:
    core_codes = list(profile["core_payment_anchors_json"])
    actual = Decimal(str(profile["profile_confidence"]))
    if not core_codes:
        return actual == Decimal("0.0000")
    if len(core_codes) > 3:
        return False
    weights = (Decimal("0.6000"), Decimal("0.2500"), Decimal("0.1500"))[: len(core_codes)]
    total = sum(weights, Decimal("0.0000"))
    expected = sum(
        (
            Decimal(str(anchors[f"{profile['sku_code']}::{code}"]["confidence"]))
            * (weight / total)
            for code, weight in zip(core_codes, weights, strict=True)
        ),
        Decimal("0.0000"),
    ).quantize(Decimal("0.0001"))
    return actual == expected


def _review_gate_valid(profile: Mapping[str, Any]) -> bool:
    review_required = bool(profile["review_required"])
    reason_payload = profile.get("review_reason_json") or {}
    reasons = set(str(reason) for reason in reason_payload.get("reasons") or ())
    detail_count = sum(
        len(reason_payload.get(key) or ())
        for key in (
            "profile_blocking_issues",
            "release_blocking_issues",
            "core_candidate_blocking_issues",
        )
    )
    if not review_required:
        return not reasons and detail_count == 0
    return bool(reasons) and reasons <= REVIEW_REASON_CODES and detail_count > 0


def assert_acceptance(comparison: Mapping[str, Mapping[str, Any]]) -> None:
    for category, result in comparison.items():
        if result["profile_added_count"] or result["profile_removed_count"]:
            raise RuntimeError(f"{category} profile set changed during decision-only shadow")
        if result["anchor_added_count"] or result["anchor_removed_count"]:
            raise RuntimeError(f"{category} anchor set changed during decision-only shadow")
        if result["non_target_changed_anchor_count"]:
            raise RuntimeError(f"{category} non-target anchor fields changed")
        if result["invalid_status_count"]:
            raise RuntimeError(f"{category} emitted legacy or invalid profile status")
        if result["core_limit_violation_count"] or result["core_family_violation_count"]:
            raise RuntimeError(f"{category} core convergence violated limit or family uniqueness")
        if result["confidence_formula_violation_count"]:
            raise RuntimeError(f"{category} profile confidence did not match selected core anchors")
        if result["review_gate_violation_count"]:
            raise RuntimeError(f"{category} review was not backed by conclusion-changing blocking issue")
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
        "# M12D-QF-12 TV/AC Profile Decision Shadow",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 范围：只比较核心锚点收敛、画像置信度、状态和复核；不修改锚点评分或发布控制。",
        "",
        "| 品类 | SKU | 受影响 SKU | 旧状态 | 新状态 | 旧复核 | 新复核 |",
        "| --- | ---: | ---: | --- | --- | ---: | ---: |",
    ]
    for category in ("TV", "AC"):
        result = payload["comparison"][category]
        lines.append(
            f"| {category} | {result['sku_count']} | {result['affected_sku_count']} | "
            f"`{result['before_status_counts']}` | `{result['after_status_counts']}` | "
            f"{result['before_review_required_count']} | {result['after_review_required_count']} |"
        )
    for category in ("TV", "AC"):
        result = payload["comparison"][category]
        lines.extend(
            [
                "",
                f"## {category}",
                "",
                f"- 状态迁移：`{result['status_migrations']}`",
                f"- 复核迁移：`{result['review_migrations']}`",
                f"- 核心数量分布：`{result['before_core_count_distribution']}` -> "
                f"`{result['after_core_count_distribution']}`",
                f"- 锚点角色迁移：`{result['anchor_role_migrations']}`",
                f"- 非目标锚点字段变化：`{result['non_target_changed_anchor_count']}`",
                f"- 非法状态：`{result['invalid_status_count']}`",
                f"- 核心上限/同族违规：`{result['core_limit_violation_count']}` / "
                f"`{result['core_family_violation_count']}`",
                f"- 置信度公式违规：`{result['confidence_formula_violation_count']}`",
                f"- 复核门槛违规：`{result['review_gate_violation_count']}`",
                f"- 未影响回归样本：`{len(result['unaffected_non_target_samples'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            f"- M12D 持久化表未变化：`{payload['downstream_guard']['unchanged']}`",
            "- 核心锚点按分数、置信度、强域数和 taxonomy priority 稳定排序，同 family 去重且最多 3 个。",
            "- 画像置信度只来自已选核心；无核心时辅助置信度单独记录，不伪装成核心置信度。",
            "- 风险锚点、普通 warning、低置信和输入缺失不自动触发复核。",
            "- TV/AC 使用各自 taxonomy；本任务未写 current/published，也未进入发布门禁。",
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
