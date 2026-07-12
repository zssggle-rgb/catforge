#!/usr/bin/env python3
"""Read-only TV/AC shadow for independent M12D purchase pressure."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import text

from app.core.database import SessionLocal
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
ANCHOR_INVARIANTS = (
    "raw_evidence_score",
    "conflict_penalty",
    "adjusted_evidence_score",
    "evidence_strength",
    "confidence",
    "role",
)
PROFILE_INVARIANTS = (
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
    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    output_markdown = Path(args.output_markdown)
    for path in (output_json, output_csv, output_markdown):
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
        if result["summary"]["sku_count"] == 0:
            failed_checks.append(f"{category.lower()}_empty")
        if result["summary"]["legacy_invariant_failures"]:
            failed_checks.append(f"{category.lower()}_legacy_changed")
        if len(result["legacy_invariant_regression_samples"]) < 20:
            failed_checks.append(f"{category.lower()}_regression_samples_below_20")
        if result["summary"]["untraced_pressure_tag_count"]:
            failed_checks.append(f"{category.lower()}_untraced_pressure")

    payload = {
        "task_id": "M12D-RP-G03",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "method": {
            "scope": "205 当前发布 TV/AC SKU，只读重建 context/candidate/legacy score 并附加购买阻力。",
            "comment_measurement": "完整维度 polarity_counts 负责量化；原始评论和 evidence_id 只负责举证。",
            "invariant": "压力标签不得修改旧证据分、角色、核心理由和画像决策。",
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
    write_json(output_json, payload)
    write_csv(output_csv, payload)
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
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
    integrated_scorer = PurchaseReasonProfileScoringService()

    level_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    limitation_counts: Counter[str] = Counter()
    pressure_skus: set[str] = set()
    pressure_anchors: list[dict[str, Any]] = []
    evidence_samples: dict[str, list[dict[str, Any]]] = {}
    invariant_failures: list[dict[str, Any]] = []
    invariant_samples: list[dict[str, Any]] = []
    no_pressure_samples: list[dict[str, Any]] = []
    untraced_pressure_tag_count = 0
    untraced_pressure_tags: list[dict[str, str]] = []

    for index, row in enumerate(rows, start=1):
        sku_code = str(row.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        legacy_anchors = [
            role_classifier.classify(evidence_scorer.score(candidate, context))
            for candidate in candidate_set.purchase_reason_candidates
        ]
        legacy_profile = profile_scorer.score(
            candidate_set=candidate_set,
            context=context,
            scored_anchors=legacy_anchors,
        )
        pressure_profile = integrated_scorer.score(
            candidate_set=candidate_set,
            context=context,
        )
        failures = compare_legacy_fields(legacy_profile, pressure_profile)
        if failures:
            invariant_failures.append({"sku_code": sku_code, "failures": failures})
        elif len(invariant_samples) < 20:
            invariant_samples.append(
                {
                    "sku_code": sku_code,
                    "display_name_cn": context.display_name_cn,
                    "status": str(pressure_profile.status),
                    "core_anchors": list(pressure_profile.core_payment_anchors_json),
                }
            )

        sku_has_pressure = False
        for anchor in pressure_profile.scored_anchors:
            level_counts[str(anchor.pressure_level)] += 1
            for limitation in anchor.comparison_limitations_json:
                limitation_counts[str(limitation.limitation_code)] += 1
            if not anchor.pressure_tags_json:
                continue
            sku_has_pressure = True
            pressure_anchors.append(
                {
                    "sku_code": sku_code,
                    "display_name_cn": context.display_name_cn,
                    "anchor_code": anchor.anchor_code,
                    "anchor_cn": anchor.anchor_cn,
                    "legacy_score": str(anchor.adjusted_evidence_score),
                    "legacy_role": str(anchor.role),
                    "pressure_level": str(anchor.pressure_level),
                    "pressure_types": [
                        str(tag.pressure_type) for tag in anchor.pressure_tags_json
                    ],
                    "comparison_limitations": [
                        str(item.limitation_code)
                        for item in anchor.comparison_limitations_json
                    ],
                }
            )
            for tag in anchor.pressure_tags_json:
                pressure_type = str(tag.pressure_type)
                type_counts[pressure_type] += 1
                if not tag.source_refs:
                    untraced_pressure_tag_count += 1
                    untraced_pressure_tags.append(
                        {
                            "sku_code": sku_code,
                            "anchor_code": anchor.anchor_code,
                            "pressure_type": pressure_type,
                        }
                    )
                samples = evidence_samples.setdefault(pressure_type, [])
                if len(samples) < 8:
                    samples.append(
                        {
                            "sku_code": sku_code,
                            "display_name_cn": context.display_name_cn,
                            "anchor_code": anchor.anchor_code,
                            "anchor_cn": anchor.anchor_cn,
                            "pressure_level": str(tag.pressure_level),
                            "summary_cn": tag.summary_cn,
                            "positive_count": tag.positive_count,
                            "negative_count": tag.negative_count,
                            "mixed_count": tag.mixed_count,
                            "source_refs": [compact_ref(ref) for ref in tag.source_refs[:5]],
                        }
                    )
        if sku_has_pressure:
            pressure_skus.add(sku_code)
        elif len(no_pressure_samples) < 20:
            no_pressure_samples.append(
                {
                    "sku_code": sku_code,
                    "display_name_cn": context.display_name_cn,
                    "status": str(pressure_profile.status),
                }
            )
        if index % 25 == 0 or index == len(rows):
            print(f"{category}: {index}/{len(rows)}", flush=True)

    return {
        "purchase_reason_version_id": str(version.purchase_reason_version_id),
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "summary": {
            "sku_count": len(rows),
            "pressure_sku_count": len(pressure_skus),
            "pressure_anchor_count": len(pressure_anchors),
            "pressure_level_counts": dict(sorted(level_counts.items())),
            "pressure_type_counts": dict(sorted(type_counts.items())),
            "comparison_limitation_counts": dict(sorted(limitation_counts.items())),
            "legacy_invariant_failures": len(invariant_failures),
            "untraced_pressure_tag_count": untraced_pressure_tag_count,
        },
        "impact_set": sorted(pressure_skus),
        "allowed_migration": "仅新增 pressure 和 comparison limitation 字段；旧评分、角色和画像决策不迁移。",
        "pressure_anchors": pressure_anchors,
        "evidence_samples_by_type": evidence_samples,
        "legacy_invariant_failures": invariant_failures,
        "untraced_pressure_tags": untraced_pressure_tags,
        "legacy_invariant_regression_samples": invariant_samples,
        "no_pressure_regression_samples": no_pressure_samples,
    }


def compare_legacy_fields(legacy: Any, pressure: Any) -> list[str]:
    failures = [
        field
        for field in PROFILE_INVARIANTS
        if getattr(legacy, field) != getattr(pressure, field)
    ]
    legacy_by_code = {anchor.anchor_code: anchor for anchor in legacy.scored_anchors}
    pressure_by_code = {anchor.anchor_code: anchor for anchor in pressure.scored_anchors}
    if set(legacy_by_code) != set(pressure_by_code):
        failures.append("anchor_set")
        return failures
    for anchor_code, legacy_anchor in legacy_by_code.items():
        pressure_anchor = pressure_by_code[anchor_code]
        for field in ANCHOR_INVARIANTS:
            if getattr(legacy_anchor, field) != getattr(pressure_anchor, field):
                failures.append(f"{anchor_code}.{field}")
    return failures


def compact_ref(ref: Any) -> dict[str, Any]:
    extra = dict(ref.extra)
    if "raw_comment_text" in extra:
        extra["raw_comment_text"] = str(extra["raw_comment_text"])[:240]
    if "comment_examples" in extra:
        extra["comment_examples"] = list(extra["comment_examples"])[:3]
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
        "legacy_score",
        "legacy_role",
        "pressure_level",
        "pressure_types",
        "comparison_limitations",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for category, result in payload["categories"].items():
            for row in result["pressure_anchors"]:
                writer.writerow(
                    {
                        **{field: row.get(field, "") for field in fields},
                        "category": category,
                        "pressure_types": "|".join(row["pressure_types"]),
                        "comparison_limitations": "|".join(
                            row["comparison_limitations"]
                        ),
                    }
                )


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-RP-G03 TV/AC 购买阻力影子测算",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 性质：205 当前发布范围只读测算；未写生产表、未发布新版本。",
        "- 评论口径：完整维度统计负责量化，原始评论及 evidence_id 负责举证。",
        "- 不变量：购买阻力与理由成立分离，压力不得修改旧评分、角色和画像决策。",
        "",
    ]
    for category, result in payload["categories"].items():
        summary = result["summary"]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- SKU：`{summary['sku_count']}`；命中阻力：`{summary['pressure_sku_count']}`。",
                f"- 阻力锚点：`{summary['pressure_anchor_count']}`；旧结果变化：`{summary['legacy_invariant_failures']}`。",
                f"- 无来源阻力标签：`{summary['untraced_pressure_tag_count']}`。",
                f"- 压力等级：`{json.dumps(summary['pressure_level_counts'], ensure_ascii=False)}`。",
                f"- 压力类型：`{json.dumps(summary['pressure_type_counts'], ensure_ascii=False)}`。",
                f"- 比较限制：`{json.dumps(summary['comparison_limitation_counts'], ensure_ascii=False)}`。",
                f"- 未影响回归样本：`{len(result['legacy_invariant_regression_samples'])}`；无压力样本：`{len(result['no_pressure_regression_samples'])}`。",
                "",
            ]
        )
    lines.extend(
        [
            "## 验收",
            "",
            f"- 三张 M12D 表前后快照一致：`{payload['downstream_guard']['unchanged']}`。",
            f"- G03 验收：`{'通过' if payload['acceptance']['passed'] else '未通过'}`。",
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
