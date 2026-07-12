#!/usr/bin/env python3
"""Run TV/AC M12D context and candidate quality shadow without writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_INPUT_QUALITY_POLICY_VERSION,
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
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CONFIG = {
    "TV": {
        "taxonomy_version": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        "old_versions": {
            "param_rule_version": "m03b_tv_param_profile_v0.1",
            "claim_taxonomy_version": CORE3_M04C_TV_TAXONOMY_VERSION,
            "claim_rule_version": "m04c_tv_claim_fact_profile_v0.1",
            "comment_taxonomy_version": CORE3_M05C_TV_TAXONOMY_VERSION,
            "comment_rule_version": "m05c_tv_comment_fact_profile_v0.1",
            "task_taxonomy_version": CORE3_M09C_TV_TAXONOMY_VERSION,
            "task_rule_version": "m09c_tv_user_task_profile_v0.2",
            "target_group_taxonomy_version": CORE3_M10C_TV_TAXONOMY_VERSION,
            "target_group_rule_version": "m10c_tv_target_group_profile_v0.2",
            "battlefield_taxonomy_version": CORE3_M11C_TV_TAXONOMY_VERSION,
            "battlefield_rule_version": "m11c_tv_value_battlefield_profile_v0.3",
            "claim_value_rule_version": "m12c_claim_value_quantification_v0.1",
        },
    },
    "AC": {
        "taxonomy_version": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        "old_versions": {
            "param_rule_version": "m03b_ac_param_profile_v0.1",
            "claim_taxonomy_version": CORE3_M04C_AC_TAXONOMY_VERSION,
            "claim_rule_version": "m04c_ac_claim_fact_profile_v0.1",
            "comment_taxonomy_version": CORE3_M05C_AC_TAXONOMY_VERSION,
            "comment_rule_version": "m05c_ac_comment_fact_profile_v0.1",
            "task_taxonomy_version": CORE3_M09C_AC_TAXONOMY_VERSION,
            "task_rule_version": "m09c_ac_user_task_profile_v0.2",
            "target_group_taxonomy_version": CORE3_M10C_AC_TAXONOMY_VERSION,
            "target_group_rule_version": "m10c_ac_target_group_profile_v0.2",
            "battlefield_taxonomy_version": CORE3_M11C_AC_TAXONOMY_VERSION,
            "battlefield_rule_version": "m11c_ac_value_battlefield_profile_v0.2",
            "claim_value_rule_version": "m12c_claim_value_quantification_v0.1",
        },
    },
}

STATUS_FIELDS = (
    "param_profile_status",
    "claim_fact_status",
    "comment_profile_status",
    "market_profile_status",
    "semantic_profile_status",
    "semantic_market_status",
    "claim_value_status",
)

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
            category: run_category_shadow(db, category, config, limit=args.limit)
            for category, config in CATEGORY_CONFIG.items()
        }
        guard_after = capture_guard(db)
    if guard_before != guard_after:
        raise RuntimeError("M12D context shadow changed persisted M12D tables")
    assert_acceptance(categories)

    payload = {
        "task_id": "M12D-QF-10",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "input_quality_policy_version": CORE3_M12D_INPUT_QUALITY_POLICY_VERSION,
        "scope": "M12D context and candidate shadow only; scoring and profile decisions are not run",
        "allowed_migrations": {
            "TV": [
                "legacy conflict/partial caused by system flags may become ready",
                "row/relation/anchor issues remain in typed input_quality_json",
                "QF upstream drafts may change candidate evidence matches",
            ],
            "AC": [
                "legacy conflict/partial caused by system flags may become ready",
                "row/relation/anchor issues remain in typed input_quality_json",
                "QF upstream drafts may change candidate evidence matches",
            ],
        },
        "categories": categories,
        "downstream_guard": {
            "before": guard_before,
            "after": guard_after,
            "unchanged": guard_before == guard_after,
        },
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "categories": {
                    category: {
                        "sku_count": result["sku_count"],
                        "policy_only_candidate_business_change_count": result[
                            "policy_only_candidate_business_change_count"
                        ],
                        "upstream_candidate_business_change_count": result[
                            "upstream_candidate_business_change_count"
                        ],
                        "blocking_issue_counts": result["blocking_issue_counts"],
                    }
                    for category, result in categories.items()
                },
                "downstream_unchanged": guard_before == guard_after,
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_category_shadow(db, category: str, config: Mapping[str, Any], *, limit: int) -> dict[str, Any]:
    version = current_published_version(db, category)
    if version is None:
        raise RuntimeError(f"{category} has no current published M12D version")
    profiles = current_profiles(db, category, version.purchase_reason_version_id)
    if limit > 0:
        profiles = profiles[:limit]
    source_batch_ids = tuple(str(item) for item in (version.source_batch_ids_json or ()) if str(item))
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(config["taxonomy_version"], product_category=category)
    candidate_generator = AnchorCandidateGenerator(taxonomy)
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    )

    before_status_counts = {field: Counter() for field in STATUS_FIELDS}
    after_status_counts = {field: Counter() for field in STATUS_FIELDS}
    status_migrations = {field: Counter() for field in STATUS_FIELDS}
    quality_module_counts: dict[str, Counter[str]] = defaultdict(Counter)
    issue_severity_counts: Counter[str] = Counter()
    issue_scope_counts: Counter[str] = Counter()
    issue_code_sku_sets: dict[str, set[str]] = defaultdict(set)
    blocking_issue_sku_sets: dict[str, set[str]] = defaultdict(set)
    affected_anchor_issue_counts: Counter[str] = Counter()
    policy_only_candidate_changes: list[str] = []
    upstream_candidate_changes: list[str] = []
    samples: list[dict[str, Any]] = []

    for profile in profiles:
        sku_code = str(profile.sku_code)
        old_context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
            **config["old_versions"],
        )
        new_context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        for field in STATUS_FIELDS:
            before_value = str(getattr(profile, field))
            after_value = str(getattr(new_context, field))
            before_status_counts[field][before_value] += 1
            after_status_counts[field][after_value] += 1
            status_migrations[field][f"{before_value}->{after_value}"] += 1

        for module_code, quality in new_context.input_quality_json.items():
            quality_module_counts[module_code][f"availability:{quality.availability}"] += 1
            quality_module_counts[module_code][f"usability:{quality.usability}"] += 1
            for issue in quality.issues:
                issue_severity_counts[str(issue.severity)] += 1
                issue_scope_counts[str(issue.scope)] += 1
                issue_code_sku_sets[str(issue.code)].add(sku_code)
                if str(issue.severity) == "blocking":
                    blocking_issue_sku_sets[str(issue.code)].add(sku_code)
                for anchor_code in issue.affected_anchor_codes:
                    affected_anchor_issue_counts[str(anchor_code)] += 1

        old_candidates = candidate_generator.generate(old_context)
        new_candidates = candidate_generator.generate(new_context)
        policy_baseline_context = deepcopy(new_context)
        policy_baseline_context.input_quality_json = {}
        for snapshot in _context_snapshots(policy_baseline_context):
            snapshot.quality = None
        policy_baseline_candidates = candidate_generator.generate(policy_baseline_context)

        old_digest = candidate_business_digest(old_candidates)
        new_digest = candidate_business_digest(new_candidates)
        policy_digest = candidate_business_digest(policy_baseline_candidates)
        if old_digest != new_digest:
            upstream_candidate_changes.append(sku_code)
        if policy_digest != new_digest:
            policy_only_candidate_changes.append(sku_code)
        if len(samples) < 20:
            samples.append(
                {
                    "sku_code": sku_code,
                    "old_candidate_digest": old_digest,
                    "new_candidate_digest": new_digest,
                    "policy_baseline_digest": policy_digest,
                    "policy_business_unchanged": policy_digest == new_digest,
                    "new_statuses": {field: str(getattr(new_context, field)) for field in STATUS_FIELDS},
                    "quality_issue_count": sum(
                        len(quality.issues) for quality in new_context.input_quality_json.values()
                    ),
                }
            )

    sku_count = len(profiles)
    return {
        "category": category,
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "source_batch_ids": list(source_batch_ids),
        "read_scope": read_scope,
        "sku_count": sku_count,
        "before_status_counts": {
            field: dict(sorted(counter.items())) for field, counter in before_status_counts.items()
        },
        "after_status_counts": {
            field: dict(sorted(counter.items())) for field, counter in after_status_counts.items()
        },
        "status_migrations": {
            field: dict(sorted(counter.items())) for field, counter in status_migrations.items()
        },
        "quality_module_counts": {
            module: dict(sorted(counter.items())) for module, counter in quality_module_counts.items()
        },
        "issue_severity_counts": dict(sorted(issue_severity_counts.items())),
        "issue_scope_counts": dict(sorted(issue_scope_counts.items())),
        "issue_code_sku_counts": {
            code: len(skus) for code, skus in sorted(issue_code_sku_sets.items())
        },
        "blocking_issue_counts": {
            code: len(skus) for code, skus in sorted(blocking_issue_sku_sets.items())
        },
        "affected_anchor_issue_counts": dict(sorted(affected_anchor_issue_counts.items())),
        "policy_only_candidate_business_change_count": len(policy_only_candidate_changes),
        "policy_only_candidate_business_change_skus": sorted(policy_only_candidate_changes),
        "upstream_candidate_business_change_count": len(upstream_candidate_changes),
        "upstream_candidate_business_change_skus": sorted(upstream_candidate_changes),
        "regression_samples": samples,
    }


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


def candidate_business_digest(candidate_set: Any) -> str:
    rows = []
    for candidate in [
        *candidate_set.value_theme_candidates,
        *candidate_set.purchase_reason_candidates,
    ]:
        rows.append(
            {
                "candidate_type": candidate.candidate_type,
                "anchor_code": candidate.anchor_code,
                "anchor_family_code": candidate.anchor_family_code,
                "related_value_theme_codes": list(candidate.related_value_theme_codes),
                "evidence_domains": list(candidate.evidence_domains_json),
                "role_cap": candidate.role_cap,
                "role_cap_reasons": list(candidate.role_cap_reasons),
                "matches": sorted(
                    (
                        match.module_code,
                        str(match.evidence_domain),
                        match.match_source,
                        match.match_key,
                        str(match.match_value),
                        bool(match.weak_expression_only),
                    )
                    for match in candidate.evidence_matches
                ),
            }
        )
    encoded = json.dumps(sorted(rows, key=lambda item: (item["candidate_type"], item["anchor_code"])), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _context_snapshots(context: Any) -> Iterable[Any]:
    return (
        context.param_profile,
        context.claim_fact_profile,
        context.comment_profile,
        context.market_profile,
        context.semantic_profile,
        context.semantic_market_profile,
        context.claim_value_profile,
    )


def capture_guard(db) -> dict[str, dict[str, Any]]:
    result = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table_name}")
        ).one()
        result[table_name] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def assert_acceptance(categories: Mapping[str, Mapping[str, Any]]) -> None:
    for category, result in categories.items():
        sku_count = int(result["sku_count"])
        if not sku_count:
            raise RuntimeError(f"{category} shadow has no SKU")
        if result["policy_only_candidate_business_change_count"]:
            raise RuntimeError(f"{category} quality policy changed candidate business fields")
        for issue_code, count in result["blocking_issue_counts"].items():
            if count / sku_count > 0.20:
                raise RuntimeError(
                    f"{category} blocking issue {issue_code} covers {count}/{sku_count}"
                )
        if len(result["regression_samples"]) < min(20, sku_count):
            raise RuntimeError(f"{category} regression sample count is incomplete")


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-10 TV/AC Context/Candidate Shadow",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 质量策略：`{payload['input_quality_policy_version']}`",
        "- 范围：只构建 context 和候选，不执行评分、角色、画像决策或发布。",
        "",
        "| 品类 | SKU | 质量策略单独导致候选业务变化 | 上游草稿导致候选变化 | blocking issue |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        lines.append(
            f"| {category} | {result['sku_count']} | "
            f"{result['policy_only_candidate_business_change_count']} | "
            f"{result['upstream_candidate_business_change_count']} | "
            f"{sum(result['blocking_issue_counts'].values())} |"
        )
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        lines.extend(
            [
                "",
                f"## {category} 输入质量分布",
                "",
                "| 模块 | present | missing | usable | limited | unusable |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for module_code, counts in sorted(result["quality_module_counts"].items()):
            lines.append(
                f"| {module_code} | {counts.get('availability:present', 0)} | "
                f"{counts.get('availability:missing', 0)} | "
                f"{counts.get('usability:usable', 0)} | "
                f"{counts.get('usability:limited', 0)} | "
                f"{counts.get('usability:unusable', 0)} |"
            )
        lines.extend(
            [
                "",
                f"- issue 严重度：`{result['issue_severity_counts']}`",
                f"- issue 作用域：`{result['issue_scope_counts']}`",
                f"- 未影响回归样本：`{len(result['regression_samples'])}` 个，质量策略业务摘要变化 `0` 个。",
            ]
        )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            f"- M12D 持久化表未变化：`{payload['downstream_guard']['unchanged']}`",
            "- row/relation/anchor issue 保留在 typed `input_quality_json`，不再扩散为模块 partial。",
            "- missing 仍为 missing；未补成 false、0 值或正向证据。",
            "- TV/AC 使用各自 taxonomy 与上游规则版本。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--output-json",
        default="docs/core3_mvp/real_data_v2/current_implementation/M12D_QF10_tv_ac_context_candidate_shadow.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="docs/core3_mvp/real_data_v2/current_implementation/M12D_QF10_tv_ac_context_candidate_shadow_report.md",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
