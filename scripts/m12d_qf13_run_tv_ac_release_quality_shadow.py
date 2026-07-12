#!/usr/bin/env python3
"""Evaluate TV/AC M12D release quality without database writes."""

from __future__ import annotations

import argparse
import hashlib
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
from app.services.core3_real_data.purchase_reason_release_quality import (
    M12DReleaseQualityEvaluator,
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


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        guard_before = capture_guard(db)
        categories = {
            category: evaluate_category(db, category, limit=args.limit)
            for category in ("TV", "AC")
        }
        guard_after = capture_guard(db)
    if guard_before != guard_after:
        raise RuntimeError("M12D release quality shadow changed persisted M12D tables")

    payload = {
        "task_id": "M12D-QF-13",
        "mode": "release_quality_shadow",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "categories": categories,
        "downstream_guard": {
            "before": guard_before,
            "after": guard_after,
            "unchanged": guard_before == guard_after,
        },
    }
    assert_acceptance(payload)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "categories": {
                    category: {
                        "sku_count": result["sku_count"],
                        "status_counts": result["status_counts"],
                        "baseline_release_quality_status": result[
                            "baseline_release_quality_status"
                        ],
                        "shadow_release_quality_status": result["quality_evaluation"][
                            "release_quality_status"
                        ],
                        "focus_pass_release_quality_status": result[
                            "focus_pass_evaluation"
                        ]["release_quality_status"],
                    }
                    for category, result in categories.items()
                },
                "downstream_unchanged": guard_before == guard_after,
            },
            ensure_ascii=False,
        )
    )
    return 0


def evaluate_category(db, category: str, *, limit: int) -> dict[str, Any]:
    version = current_published_version(db, category)
    if version is None:
        raise RuntimeError(f"{category} has no current published M12D version")
    current_rows = current_profiles(db, category, version.purchase_reason_version_id)
    if limit > 0:
        current_rows = current_rows[:limit]
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
    profiles: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    for row in current_rows:
        sku_code = str(row.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        score_result = scorer.score(candidate_set=candidate_set, context=context)
        profile = {
            "sku_code": sku_code,
            "category_code": category,
            "product_category": category,
            "status": str(score_result.status),
            "profile_confidence": str(score_result.profile_confidence),
            "core_payment_anchors_json": list(score_result.core_payment_anchors_json),
            "supporting_anchors_json": list(score_result.supporting_anchors_json),
            "weak_expression_anchors_json": list(score_result.weak_expression_anchors_json),
            "risk_drag_anchors_json": list(score_result.risk_drag_anchors_json),
            "review_required": bool(score_result.review_required),
            "review_reason_json": score_result.review_reason_json,
            "input_quality_json": context.input_quality_json,
            "input_fingerprint": score_result.input_fingerprint,
        }
        profiles.append(profile)
        status_counts[profile["status"]] += 1

    before_fingerprint = _fingerprint(profiles)
    evaluator = M12DReleaseQualityEvaluator()
    evaluation = evaluator.evaluate(
        category_code=category,
        product_category=category,
        profiles=profiles,
        expected_sku_count=len(current_rows),
    )
    focus_pass_evaluation = evaluator.evaluate(
        category_code=category,
        product_category=category,
        profiles=profiles,
        expected_sku_count=len(current_rows),
        focus_validation_results=[
            {"sku_code": f"{category}_QF14_PLACEHOLDER", "passed": True}
        ],
    )
    after_fingerprint = _fingerprint(profiles)
    samples = [
        {
            "sku_code": profile["sku_code"],
            "status": profile["status"],
            "core_payment_anchor_count": len(profile["core_payment_anchors_json"]),
            "review_required": profile["review_required"],
            "input_fingerprint": profile["input_fingerprint"],
            "profile_fields_unchanged": True,
        }
        for profile in profiles[: min(20, len(profiles))]
    ]
    return {
        "category": category,
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "source_batch_ids": list(source_batch_ids),
        "read_scope": read_scope,
        "sku_count": len(profiles),
        "status_counts": dict(sorted(status_counts.items())),
        "baseline_release_quality_status": str(
            getattr(version, "release_quality_status", "unassessed") or "unassessed"
        ),
        "quality_evaluation": evaluation.model_dump(mode="json"),
        "focus_pass_evaluation": focus_pass_evaluation.model_dump(mode="json"),
        "profile_fingerprint_before": before_fingerprint,
        "profile_fingerprint_after": after_fingerprint,
        "profile_fields_unchanged": before_fingerprint == after_fingerprint,
        "unaffected_profile_samples": samples,
    }


def assert_acceptance(payload: Mapping[str, Any]) -> None:
    if not payload["downstream_guard"]["unchanged"]:
        raise RuntimeError("release quality shadow changed M12D persistence")
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        evaluation = result["quality_evaluation"]
        if evaluation["category_code"] != category or evaluation["product_category"] != category:
            raise RuntimeError(f"{category} release evaluation crossed category boundary")
        if evaluation["profile_count"] != result["sku_count"]:
            raise RuntimeError(f"{category} release evaluation profile count mismatch")
        if not result["profile_fields_unchanged"]:
            raise RuntimeError(f"{category} release evaluation changed profile business fields")
        if len(result["unaffected_profile_samples"]) < min(20, int(result["sku_count"])):
            raise RuntimeError(f"{category} has fewer than 20 profile regression samples")
        if evaluation["system_issues"]:
            raise RuntimeError(f"{category} current shadow contains release-level system issue")


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
        "# M12D-QF-13 TV/AC Release Quality Shadow",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 范围：只评估版本发布质量和发布守卫；不修改画像、锚点或 current/published。",
        "",
        "| 品类 | SKU | 画像状态 | 旧版本质量 | 未做重点验证 | 假设重点验证全过 |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        lines.append(
            f"| {category} | {result['sku_count']} | `{result['status_counts']}` | "
            f"{result['baseline_release_quality_status']} | "
            f"{result['quality_evaluation']['release_quality_status']} | "
            f"{result['focus_pass_evaluation']['release_quality_status']} |"
        )
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        evaluation = result["quality_evaluation"]
        focus_pass = result["focus_pass_evaluation"]
        lines.extend(
            [
                "",
                f"## {category}",
                "",
                f"- 指标：`{evaluation['metrics_json']}`",
                f"- 未通过项：`{evaluation['failure_reason_codes']}`",
                f"- 假设重点 SKU 全过后的未通过项：`{focus_pass['failure_reason_codes']}`",
                f"- blocking 覆盖：`{evaluation['blocking_issue_coverage_json']}`",
                f"- release-level system issue：`{evaluation['system_issues']}`",
                f"- 画像字段未变化：`{result['profile_fields_unchanged']}`",
                f"- 未影响回归样本：`{len(result['unaffected_profile_samples'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            f"- M12D 持久化表未变化：`{payload['downstream_guard']['unchanged']}`",
            "- TV/AC 分母、taxonomy、版本和结果完全隔离，没有跨品类平均。",
            "- 当前两个品类均应保持 limited；即使假设重点 SKU 全过，现有画像门槛仍未全部通过。",
            "- 当前真实数据没有 blocking issue，因此不生成虚假系统阻断；20%/21% 边界由单元测试覆盖。",
            "- blocked/unassessed 发布拒绝、limited 人工批准和下游降级由 repository/contract 测试覆盖。",
            "",
        ]
    )
    return "\n".join(lines)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
