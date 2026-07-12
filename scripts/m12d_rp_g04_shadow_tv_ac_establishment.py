#!/usr/bin/env python3
"""Read-only TV/AC shadow for M12D establishment and user validation."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.core3_real_data.constants import (
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    M12DAnchorRole,
    M12DReasonEstablishmentStatus,
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
from app.services.core3_real_data.purchase_reason_pressure import (
    PurchasePressureClassifier,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (
    EvidenceStrengthScorer,
    ProfileConfidenceScorer,
    PurchaseReasonProfileScoringService,
    ReasonRoleClassifier,
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
ANCHOR_LEGACY_INVARIANTS = (
    "raw_evidence_score",
    "conflict_penalty",
    "adjusted_evidence_score",
    "evidence_strength",
    "confidence",
    "role",
)
PROFILE_LEGACY_INVARIANTS = (
    "status",
    "profile_confidence",
    "confidence_level",
    "core_payment_anchors_json",
    "supporting_anchors_json",
    "weak_expression_anchors_json",
    "risk_drag_anchors_json",
)


def main() -> int:
    args = parse_args()
    outputs = [
        Path(args.output_json),
        Path(args.output_csv),
        Path(args.output_markdown),
    ]
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        before = capture_guard(db)
        categories = {
            category: shadow_category(db, category)
            for category in ("TV", "AC")
        }
        after = capture_guard(db)
    guard_unchanged = before == after

    failed_checks = []
    if not guard_unchanged:
        failed_checks.append("downstream_tables_changed")
    for category, result in categories.items():
        summary = result["summary"]
        if summary["sku_count"] == 0:
            failed_checks.append(f"{category.lower()}_empty")
        for key in (
            "legacy_invariant_failure_count",
            "pressure_invariant_failure_count",
            "core_below_7_count",
            "proposition_core_eligible_count",
            "unassessed_anchor_count",
            "core_boundary_failure_count",
            "untraced_core_count",
        ):
            if summary[key]:
                failed_checks.append(f"{category.lower()}_{key}")
        if len(result["legacy_invariant_regression_samples"]) < 20:
            failed_checks.append(f"{category.lower()}_regression_samples_below_20")

    payload = {
        "task_id": "M12D-RP-G04",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "method": {
            "scope": "205 当前发布 TV/AC SKU，只读重建并写入内存中的成立、承接和核心资格字段。",
            "positive_only": "评论只读同锚点正向事实；M12C 只读同理由 claim 的正向/中性角色；普通负面只保留 G03 pressure。",
            "thresholds": "标准 9 分；基线无核心时 8 分兜底；理由边界通过时最低 7 分，低于 7 分禁止核心。",
            "g04_boundary": "不修改旧角色、SKU 状态、版本质量和竞品消费。",
        },
        "categories": categories,
        "downstream_guard": {
            "before": before,
            "after": after,
            "unchanged": guard_unchanged,
        },
        "acceptance": {
            "passed": not failed_checks,
            "failed_checks": failed_checks,
        },
    }
    write_json(outputs[0], payload)
    write_csv(outputs[1], payload)
    outputs[2].write_text(render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok" if not failed_checks else "failed",
                "categories": {
                    category: result["summary"]
                    for category, result in categories.items()
                },
                "downstream_unchanged": guard_unchanged,
                "failed_checks": failed_checks,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failed_checks else 1


def shadow_category(db: Any, category: str) -> dict[str, Any]:
    version = current_published_version(db, category)
    if version is None:
        raise RuntimeError(f"{category} has no current published M12D version")
    rows = current_profiles(db, category, str(version.purchase_reason_version_id))
    source_batch_ids = tuple(
        str(value)
        for value in (version.source_batch_ids_json or ())
        if str(value)
    )
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CATEGORY_TAXONOMY[category],
        product_category=category,
    )
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(
            db=db,
            project_id=PROJECT_ID,
            category_code=category,
        )
    )
    generator = AnchorCandidateGenerator(taxonomy)
    evidence_scorer = EvidenceStrengthScorer()
    role_classifier = ReasonRoleClassifier()
    profile_scorer = ProfileConfidenceScorer()
    pressure_classifier = PurchasePressureClassifier()
    integrated_scorer = PurchaseReasonProfileScoringService()

    status_counts: Counter[str] = Counter()
    validation_counts: Counter[str] = Counter()
    threshold_counts: Counter[str] = Counter()
    status_anchor_counts: dict[str, Counter[str]] = defaultdict(Counter)
    core_eligible_skus: set[str] = set()
    proposition_skus: set[str] = set()
    rejected_misalignment_skus: set[str] = set()
    rows_output: list[dict[str, Any]] = []
    evidence_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    legacy_failures: list[dict[str, Any]] = []
    pressure_failures: list[dict[str, Any]] = []
    invariant_samples: list[dict[str, Any]] = []
    core_below_7: list[dict[str, str]] = []
    proposition_core_eligible: list[dict[str, str]] = []
    unassessed: list[dict[str, str]] = []
    core_boundary_failures: list[dict[str, str]] = []
    untraced_core: list[dict[str, str]] = []

    for index, row in enumerate(rows, start=1):
        sku_code = str(row.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        candidates = {
            candidate.anchor_code: candidate
            for candidate in candidate_set.purchase_reason_candidates
        }
        legacy_anchors = [
            role_classifier.classify(evidence_scorer.score(candidate, context))
            for candidate in candidate_set.purchase_reason_candidates
        ]
        legacy_pressure_anchors = [
            pressure_classifier.classify(
                candidate=candidates[anchor.anchor_code],
                context=context,
                scored_anchor=anchor,
            )
            for anchor in legacy_anchors
        ]
        legacy_profile = profile_scorer.score(
            candidate_set=candidate_set,
            context=context,
            scored_anchors=legacy_pressure_anchors,
        )
        legacy_profile = pressure_classifier.summarize_profile(legacy_profile)
        result = integrated_scorer.score(
            candidate_set=candidate_set,
            context=context,
        )

        legacy_diff = compare_legacy_fields(legacy_profile, result)
        pressure_diff = compare_pressure_fields(legacy_profile, result)
        if legacy_diff:
            legacy_failures.append({"sku_code": sku_code, "failures": legacy_diff})
        if pressure_diff:
            pressure_failures.append({"sku_code": sku_code, "failures": pressure_diff})
        if not legacy_diff and not pressure_diff and len(invariant_samples) < 20:
            invariant_samples.append(
                {
                    "sku_code": sku_code,
                    "display_name_cn": context.display_name_cn,
                    "legacy_status": str(result.status),
                    "legacy_core_anchors": list(result.core_payment_anchors_json),
                }
            )

        for anchor in result.scored_anchors:
            status = str(anchor.establishment_status)
            validation = str(anchor.user_validation_status)
            threshold = str(
                anchor.role_reason_json.get("establishment_threshold_path") or "none"
            )
            status_counts[status] += 1
            validation_counts[validation] += 1
            threshold_counts[threshold] += 1
            status_anchor_counts[status][anchor.anchor_code] += 1
            if anchor.core_eligible:
                core_eligible_skus.add(sku_code)
            if status == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value:
                proposition_skus.add(sku_code)
            if "evidence_misalignment" in anchor.core_ineligible_reasons_json:
                rejected_misalignment_skus.add(sku_code)
            if anchor.core_eligible and Decimal(str(anchor.establishment_score or 0)) < Decimal("7"):
                core_below_7.append({"sku_code": sku_code, "anchor_code": anchor.anchor_code})
            if status == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value and anchor.core_eligible:
                proposition_core_eligible.append({"sku_code": sku_code, "anchor_code": anchor.anchor_code})
            if status == M12DReasonEstablishmentStatus.UNASSESSED.value:
                unassessed.append({"sku_code": sku_code, "anchor_code": anchor.anchor_code})
            if anchor.core_eligible and not bool(
                anchor.role_reason_json.get("business_boundary_passed")
            ):
                core_boundary_failures.append({"sku_code": sku_code, "anchor_code": anchor.anchor_code})
            if anchor.core_eligible and (
                not anchor.user_support_evidence_json
                or not anchor.proposition_evidence_json
            ):
                untraced_core.append({"sku_code": sku_code, "anchor_code": anchor.anchor_code})

            compact = {
                "sku_code": sku_code,
                "display_name_cn": context.display_name_cn,
                "anchor_code": anchor.anchor_code,
                "anchor_cn": anchor.anchor_cn,
                "legacy_role": str(anchor.role),
                "legacy_adjusted_score": str(anchor.adjusted_evidence_score),
                "establishment_status": status,
                "establishment_score": str(anchor.establishment_score),
                "establishment_domains": [
                    str(domain) for domain in anchor.establishment_domains_json
                ],
                "user_validation_status": validation,
                "core_eligible": bool(anchor.core_eligible),
                "threshold_path": threshold,
                "business_boundary_passed": bool(
                    anchor.role_reason_json.get("business_boundary_passed")
                ),
                "core_ineligible_reasons": list(anchor.core_ineligible_reasons_json),
                "pressure_level": str(anchor.pressure_level),
            }
            rows_output.append(compact)
            sample_key = threshold if threshold != "none" else status
            if len(evidence_samples[sample_key]) < 10:
                evidence_samples[sample_key].append(
                    {
                        **compact,
                        "proposition_evidence": [
                            compact_ref(ref)
                            for ref in anchor.proposition_evidence_json[:4]
                        ],
                        "user_support_evidence": [
                            compact_ref(ref)
                            for ref in anchor.user_support_evidence_json[:4]
                        ],
                    }
                )
        if index % 25 == 0 or index == len(rows):
            print(f"{category}: {index}/{len(rows)}", flush=True)

    anchors_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in rows_output:
        anchors_by_sku[anchor["sku_code"]].append(anchor)
    baseline_no_core_skus = {
        sku_code
        for sku_code, anchors in anchors_by_sku.items()
        if not any(anchor["legacy_role"] == M12DAnchorRole.CORE_PAYMENT.value for anchor in anchors)
    }
    new_core_eligible_skus = {
        sku_code
        for sku_code in baseline_no_core_skus
        if any(anchor["core_eligible"] for anchor in anchors_by_sku[sku_code])
    }
    new_core_threshold_counts = Counter(
        anchor["threshold_path"]
        for sku_code in new_core_eligible_skus
        for anchor in anchors_by_sku[sku_code]
        if anchor["core_eligible"]
    )
    new_core_anchor_counts = Counter(
        anchor["anchor_code"]
        for sku_code in new_core_eligible_skus
        for anchor in anchors_by_sku[sku_code]
        if anchor["core_eligible"]
    )

    return {
        "purchase_reason_version_id": str(version.purchase_reason_version_id),
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "summary": {
            "sku_count": len(rows),
            "anchor_count": len(rows_output),
            "establishment_status_counts": dict(sorted(status_counts.items())),
            "user_validation_status_counts": dict(sorted(validation_counts.items())),
            "threshold_path_counts": dict(sorted(threshold_counts.items())),
            "core_eligible_sku_count": len(core_eligible_skus),
            "baseline_no_core_sku_count": len(baseline_no_core_skus),
            "new_core_eligible_from_no_core_sku_count": len(new_core_eligible_skus),
            "remaining_no_core_sku_count": len(
                baseline_no_core_skus - new_core_eligible_skus
            ),
            "new_core_threshold_path_counts": dict(
                sorted(new_core_threshold_counts.items())
            ),
            "new_core_anchor_counts": dict(new_core_anchor_counts.most_common()),
            "proposition_sku_count": len(proposition_skus),
            "rejected_misalignment_sku_count": len(rejected_misalignment_skus),
            "legacy_invariant_failure_count": len(legacy_failures),
            "pressure_invariant_failure_count": len(pressure_failures),
            "core_below_7_count": len(core_below_7),
            "proposition_core_eligible_count": len(proposition_core_eligible),
            "unassessed_anchor_count": len(unassessed),
            "core_boundary_failure_count": len(core_boundary_failures),
            "untraced_core_count": len(untraced_core),
        },
        "status_anchor_counts": {
            status: dict(counter.most_common())
            for status, counter in sorted(status_anchor_counts.items())
        },
        "impact_sets": {
            "core_eligible_skus": sorted(core_eligible_skus),
            "baseline_no_core_skus": sorted(baseline_no_core_skus),
            "new_core_eligible_from_no_core_skus": sorted(new_core_eligible_skus),
            "remaining_no_core_skus": sorted(
                baseline_no_core_skus - new_core_eligible_skus
            ),
            "proposition_skus": sorted(proposition_skus),
            "rejected_misalignment_skus": sorted(rejected_misalignment_skus),
        },
        "allowed_migration": "仅新增 establishment/user validation/core eligibility；旧角色、SKU 状态和 G03 pressure 不迁移。",
        "anchors": rows_output,
        "evidence_samples": dict(evidence_samples),
        "legacy_invariant_failures": legacy_failures,
        "pressure_invariant_failures": pressure_failures,
        "legacy_invariant_regression_samples": invariant_samples,
        "invalid_core_samples": {
            "below_7": core_below_7,
            "proposition_core": proposition_core_eligible,
            "unassessed": unassessed,
            "boundary_failure": core_boundary_failures,
            "untraced": untraced_core,
        },
    }


def compare_legacy_fields(legacy: Any, result: Any) -> list[str]:
    failures = [
        field
        for field in PROFILE_LEGACY_INVARIANTS
        if getattr(legacy, field) != getattr(result, field)
    ]
    legacy_by_code = {anchor.anchor_code: anchor for anchor in legacy.scored_anchors}
    result_by_code = {anchor.anchor_code: anchor for anchor in result.scored_anchors}
    if set(legacy_by_code) != set(result_by_code):
        failures.append("anchor_set")
        return failures
    for code, legacy_anchor in legacy_by_code.items():
        result_anchor = result_by_code[code]
        for field in ANCHOR_LEGACY_INVARIANTS:
            if getattr(legacy_anchor, field) != getattr(result_anchor, field):
                failures.append(f"{code}.{field}")
    return failures


def compare_pressure_fields(legacy: Any, result: Any) -> list[str]:
    failures = []
    if legacy.pressure_summary_json != result.pressure_summary_json:
        failures.append("profile.pressure_summary_json")
    legacy_by_code = {anchor.anchor_code: anchor for anchor in legacy.scored_anchors}
    result_by_code = {anchor.anchor_code: anchor for anchor in result.scored_anchors}
    for code, legacy_anchor in legacy_by_code.items():
        result_anchor = result_by_code.get(code)
        if result_anchor is None:
            continue
        for field in (
            "pressure_level",
            "pressure_tags_json",
            "pressure_summary_cn",
            "comparison_limitations_json",
        ):
            if getattr(legacy_anchor, field) != getattr(result_anchor, field):
                failures.append(f"{code}.{field}")
    return failures


def compact_ref(ref: Any) -> dict[str, Any]:
    extra = dict(ref.extra)
    if "raw_comment_text" in extra:
        extra["raw_comment_text"] = str(extra["raw_comment_text"])[:200]
    if "positive_examples" in extra:
        extra["positive_examples"] = list(extra["positive_examples"])[:3]
    return {
        "module_code": str(ref.module_code),
        "table_name": ref.table_name,
        "record_id": ref.record_id,
        "result_hash": ref.result_hash,
        "extra": extra,
    }


def current_published_version(db: Any, category: str) -> Any:
    return db.execute(
        text(
            "SELECT purchase_reason_version_id, source_batch_ids_json "
            "FROM core3_purchase_reason_profile_version "
            "WHERE project_id=:project_id AND category_code=:category "
            "AND product_category=:category AND release_status='published' "
            "AND is_current IS TRUE ORDER BY published_at DESC LIMIT 1"
        ),
        {"project_id": PROJECT_ID, "category": category},
    ).first()


def current_profiles(db: Any, category: str, version_id: str) -> list[Any]:
    return list(
        db.execute(
            text(
                "SELECT sku_code FROM core3_sku_purchase_reason_profile "
                "WHERE project_id=:project_id AND category_code=:category "
                "AND product_category=:category AND purchase_reason_version_id=:version_id "
                "AND is_current IS TRUE ORDER BY sku_code"
            ),
            {"project_id": PROJECT_ID, "category": category, "version_id": version_id},
        )
    )


def capture_guard(db: Any) -> dict[str, dict[str, Any]]:
    result = {}
    for table in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table}")
        ).one()
        result[table] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, payload: Mapping[str, Any]) -> None:
    fields = (
        "category",
        "sku_code",
        "display_name_cn",
        "anchor_code",
        "anchor_cn",
        "legacy_role",
        "legacy_adjusted_score",
        "establishment_status",
        "establishment_score",
        "establishment_domains",
        "user_validation_status",
        "core_eligible",
        "threshold_path",
        "business_boundary_passed",
        "core_ineligible_reasons",
        "pressure_level",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for category, result in payload["categories"].items():
            for row in result["anchors"]:
                writer.writerow(
                    {
                        **{field: row.get(field, "") for field in fields},
                        "category": category,
                        "establishment_domains": "|".join(
                            row["establishment_domains"]
                        ),
                        "core_ineligible_reasons": "|".join(
                            row["core_ineligible_reasons"]
                        ),
                    }
                )


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-RP-G04 TV/AC 成立度与用户承接影子测算",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 性质：205 当前发布范围只读测算；未写生产表、未改变 current。",
        "- 成立分：只读正向、同锚点证据；普通负面和购买阻力不扣成立分。",
        "- 本任务只填充新 contract；旧角色、SKU 状态、版本质量和竞品结果保持不变。",
        "",
    ]
    for category, result in payload["categories"].items():
        summary = result["summary"]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- SKU：`{summary['sku_count']}`；锚点：`{summary['anchor_count']}`。",
                f"- 成立状态：`{json.dumps(summary['establishment_status_counts'], ensure_ascii=False)}`。",
                f"- 用户承接：`{json.dumps(summary['user_validation_status_counts'], ensure_ascii=False)}`。",
                f"- 门槛路径：`{json.dumps(summary['threshold_path_counts'], ensure_ascii=False)}`。",
                f"- 至少一个 core eligible：`{summary['core_eligible_sku_count']}` SKU；至少一个 proposition：`{summary['proposition_sku_count']}` SKU。",
                f"- 基线无核心：`{summary['baseline_no_core_sku_count']}`；其中新增核心资格：`{summary['new_core_eligible_from_no_core_sku_count']}`；仍无核心资格：`{summary['remaining_no_core_sku_count']}`。",
                f"- 无核心 SKU 的新增门槛路径：`{json.dumps(summary['new_core_threshold_path_counts'], ensure_ascii=False)}`。",
                f"- 评论错配 SKU：`{summary['rejected_misalignment_sku_count']}`。",
                f"- 旧结果变化：`{summary['legacy_invariant_failure_count']}`；G03 pressure 变化：`{summary['pressure_invariant_failure_count']}`。",
                f"- 低于 7 分核心：`{summary['core_below_7_count']}`；proposition 核心：`{summary['proposition_core_eligible_count']}`；无来源核心：`{summary['untraced_core_count']}`。",
                f"- 未影响回归样本：`{len(result['legacy_invariant_regression_samples'])}`。",
                "",
            ]
        )
    lines.extend(
        [
            "## 验收",
            "",
            f"- 三张 M12D 表前后快照一致：`{payload['downstream_guard']['unchanged']}`。",
            f"- G04 验收：`{'通过' if payload['acceptance']['passed'] else '未通过'}`。",
            f"- 未通过项：`{payload['acceptance']['failed_checks']}`。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-markdown", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
