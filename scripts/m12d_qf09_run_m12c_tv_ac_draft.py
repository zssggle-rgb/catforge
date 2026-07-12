#!/usr/bin/env python3
"""Rebuild and validate TV/AC M12C claim-scoped quality drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M12C_AC_RULE_VERSION,
    CORE3_M12C_TV_RULE_VERSION,
)
from app.services.core3_real_data.m12c_claim_value_quantification_runner import (
    M12CClaimValueQuantificationRunner,
)
from app.services.core3_real_data.m12c_claim_value_quantification_service import (
    ANALYSIS_POPULATION_READY_WITH_COMMENT,
    MARKET_WINDOW_FULL_OBSERVED,
    M12C_AMOUNT_LIMITATION_FLAGS,
    M12C_RELATIVE_COMPARISON_LIMITATION_FLAGS,
    assess_m12c_claim_value_quality,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
OLD_RULE_VERSION = "m12c_claim_value_quantification_v0.1"
CATEGORY_CONFIG = {
    "TV": {
        "batches": (
            "m00_20260613004311_d548f6dc",
            "m00_20260619084551_857df63b",
        ),
        "rule_version": CORE3_M12C_TV_RULE_VERSION,
        "market_scope_count": 377,
    },
    "AC": {
        "batches": ("m00_20260624000202_1150a669",),
        "rule_version": CORE3_M12C_AC_RULE_VERSION,
        "market_scope_count": 155,
    },
}

M12C_MODELS = (
    entities.Core3ClaimValueContextPool,
    entities.Core3ClaimValuePoolMetric,
    entities.Core3SkuClaimValueQuantification,
    entities.Core3SkuClaimContributionAttribution,
    entities.Core3ClaimValueDimensionSummary,
    entities.Core3ClaimValueReviewIssue,
)

DOWNSTREAM_TABLES = (
    "core3_sku_purchase_reason_profile",
    "core3_sku_purchase_reason_anchor",
)

QUANT_BUSINESS_FIELDS = (
    "claim_value_role",
    "claim_evidence_strength",
    "param_support_strength",
    "comment_support_strength",
    "semantic_support_strength",
    "estimated_price_premium_abs",
    "estimated_weekly_sales_lift_abs",
    "estimated_weekly_sales_amount_lift_abs",
    "contribution_share_in_sku",
    "attribution_confidence",
    "evidence_ids_json",
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal(expire_on_commit=False) as db:
        downstream_before = capture_downstream_guard(db)
        before = {
            category: capture_category(db, category, OLD_RULE_VERSION)
            for category in CATEGORY_CONFIG
        }
        run_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if not args.write_draft and output_json.exists():
            existing_payload = json.loads(output_json.read_text(encoding="utf-8"))
            for category, rows in (existing_payload.get("run_results") or {}).items():
                run_results[category].extend(rows)
        if args.write_draft:
            for category, config in CATEGORY_CONFIG.items():
                for batch_id in config["batches"]:
                    result = M12CClaimValueQuantificationRunner(db).run_batch(
                        project_id=PROJECT_ID,
                        category_code=category,
                        batch_id=batch_id,
                        product_category=category,
                        analysis_population=ANALYSIS_POPULATION_READY_WITH_COMMENT,
                        market_window=MARKET_WINDOW_FULL_OBSERVED,
                        rule_version=config["rule_version"],
                    )
                    status = result.status.value if hasattr(result.status, "value") else str(result.status)
                    run_results[category].append(
                        {
                            "batch_id": batch_id,
                            "status": status,
                            "input_count": result.input_count,
                            "output_count": result.output_count,
                            "warnings": list(result.warnings),
                            "review_issue_count": len(result.review_issues),
                            "summary": result.summary_json,
                        }
                    )
                    if status in {"failed", "blocked"}:
                        raise RuntimeError(f"{category} {batch_id} M12C draft failed: {result.warnings}")
                    db.commit()
        after = {
            category: capture_category(db, category, config["rule_version"])
            for category, config in CATEGORY_CONFIG.items()
        }
        downstream_after = capture_downstream_guard(db)

    comparisons = {
        category: compare_category(before[category], after[category])
        for category in CATEGORY_CONFIG
    }
    assert_acceptance(after, comparisons, run_results)
    if downstream_before != downstream_after:
        raise RuntimeError("M12D tables changed during M12C draft rebuild")

    payload = {
        "task_id": "M12D-QF-09",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": "M12C claim/context quality and quantification boundary only",
        "write_draft": args.write_draft,
        "policy": {
            "value_existence_independent_from_amount_quantification": True,
            "amount_limitation_scope": "claim_context_pool",
            "single_sku_comparison_scope": "claim_context_relative_comparison",
            "profile_blocking_from_local_limitations": False,
            "non_quantifiable_amounts_forced_zero": True,
        },
        "allowed_migrations": {
            "TV": [
                "flag-only partial SKU becomes usable for value judgement",
                "amount-limited claim rows remain non-quantifiable and zero-valued",
                "upstream QF drafts may change claim roles and evidence-derived business values",
            ],
            "AC": [
                "flag-only partial SKU becomes usable for value judgement",
                "amount-limited claim rows remain non-quantifiable and zero-valued",
                "upstream QF drafts may change claim roles and evidence-derived business values",
            ],
        },
        "before": {key: compact_capture(value) for key, value in before.items()},
        "after": {key: compact_capture(value) for key, value in after.items()},
        "comparisons": comparisons,
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
                "comparisons": comparisons,
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
    captured: dict[str, Any] = {
        "category": category,
        "rule_version": rule_version,
        "market_scope_count": config["market_scope_count"],
    }
    for model in M12C_MODELS:
        captured[model.__tablename__] = list(
            db.scalars(
                select(model).where(
                    model.project_id == PROJECT_ID,
                    model.category_code == category,
                    model.product_category == category,
                    model.batch_id.in_(config["batches"]),
                    model.rule_version == rule_version,
                    model.is_current.is_(True),
                )
            )
        )
    return captured


def compact_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    rows = capture[entities.Core3SkuClaimValueQuantification.__tablename__]
    issues = capture[entities.Core3ClaimValueReviewIssue.__tablename__]
    by_sku = group_by_sku(rows)
    flag_counts = Counter(
        str(flag)
        for row in rows
        for flag in (row.quality_flags_json or ())
    )
    legacy_partial = {
        sku for sku, sku_rows in by_sku.items() if any(row.quality_flags_json for row in sku_rows)
    }
    usable = {
        sku
        for sku, sku_rows in by_sku.items()
        if assess_m12c_claim_value_quality(sku_rows)["usability"] == "usable"
    }
    return {
        "rule_version": capture["rule_version"],
        "market_scope_count": capture["market_scope_count"],
        "table_counts": {
            model.__tablename__: len(capture[model.__tablename__]) for model in M12C_MODELS
        },
        "sku_count": len(by_sku),
        "missing_sku_count": capture["market_scope_count"] - len(by_sku),
        "legacy_status_counts": {
            "partial": len(legacy_partial),
            "ready": len(by_sku) - len(legacy_partial),
            "missing": capture["market_scope_count"] - len(by_sku),
        },
        "claim_scoped_status_counts": {
            "usable": len(usable),
            "missing": capture["market_scope_count"] - len(by_sku),
        },
        "role_counts": dict(sorted(Counter(row.claim_value_role for row in rows).items())),
        "quality_flag_counts": dict(sorted(flag_counts.items())),
        "amount_limited_row_count": sum(is_amount_limited(row) for row in rows),
        "relative_limited_row_count": sum(is_relative_limited(row) for row in rows),
        "non_quantifiable_nonzero_row_count": sum(
            is_amount_limited(row) and has_nonzero_amount(row) for row in rows
        ),
        "quality_assessment_row_count": sum(
            bool((row.supporting_dimensions_json or {}).get("quality_assessment")) for row in rows
        ),
        "review_issue_count": len(issues),
        "review_issue_scope_counts": dict(sorted(Counter(row.issue_scope for row in issues).items())),
        "review_issue_level_counts": dict(sorted(Counter(row.issue_level for row in issues).items())),
        "quant_business_digest": digest_rows(rows),
    }


def compare_category(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_compact = compact_capture(before)
    after_compact = compact_capture(after)
    after_rows = after[entities.Core3SkuClaimValueQuantification.__tablename__]
    before_rows = before[entities.Core3SkuClaimValueQuantification.__tablename__]
    before_skus = set(group_by_sku(before_rows))
    after_by_sku = group_by_sku(after_rows)
    after_skus = set(after_by_sku)
    legacy_partial = [
        sku for sku, rows in after_by_sku.items() if any(row.quality_flags_json for row in rows)
    ]
    migrated = [
        sku
        for sku in legacy_partial
        if assess_m12c_claim_value_quality(after_by_sku[sku])["usability"] == "usable"
    ]
    no_unexpected_review = all(
        not assess_m12c_claim_value_quality(rows)["review_required"]
        for rows in after_by_sku.values()
    )
    return {
        "flag_only_partial_to_usable_count": len(migrated),
        "flag_only_partial_to_usable_skus": sorted(migrated),
        "unexpected_profile_review_count": 0 if no_unexpected_review else 1,
        "non_quantifiable_nonzero_row_count": after_compact["non_quantifiable_nonzero_row_count"],
        "quality_assessment_coverage": (
            f"{after_compact['quality_assessment_row_count']}/{after_compact['table_counts'][entities.Core3SkuClaimValueQuantification.__tablename__]}"
        ),
        "coverage_lost_count": len(before_skus - after_skus),
        "coverage_lost_skus": sorted(before_skus - after_skus),
        "coverage_gained_count": len(after_skus - before_skus),
        "coverage_gained_skus": sorted(after_skus - before_skus),
        "net_coverage_change": len(after_skus) - len(before_skus),
        "new_missing_rate": str(
            Decimal(len(before_skus - after_skus))
            / Decimal(max(int(after["market_scope_count"]), 1))
        ),
        "upstream_business_change_count": compare_business_rows(before, after),
        "regression_samples": regression_samples(after_rows, limit=20),
        "before_legacy_status_counts": before_compact["legacy_status_counts"],
        "after_claim_scoped_status_counts": after_compact["claim_scoped_status_counts"],
    }


def compare_business_rows(before: Mapping[str, Any], after: Mapping[str, Any]) -> int:
    before_rows = {
        row_key(row): row
        for row in before[entities.Core3SkuClaimValueQuantification.__tablename__]
    }
    after_rows = {
        row_key(row): row
        for row in after[entities.Core3SkuClaimValueQuantification.__tablename__]
    }
    return sum(
        key not in before_rows
        or any(normalize(getattr(row, field)) != normalize(getattr(before_rows[key], field)) for field in QUANT_BUSINESS_FIELDS)
        for key, row in after_rows.items()
    )


def regression_samples(rows: Sequence[Any], *, limit: int) -> list[dict[str, Any]]:
    by_sku = group_by_sku(rows)
    result = []
    for sku in sorted(by_sku)[:limit]:
        sku_rows = by_sku[sku]
        result.append(
            {
                "sku_code": sku,
                "row_count": len(sku_rows),
                "role_digest": digest_values((row.claim_code, row.context_code, row.claim_value_role) for row in sku_rows),
                "amount_guard_pass": not any(is_amount_limited(row) and has_nonzero_amount(row) for row in sku_rows),
                "quality_usability": assess_m12c_claim_value_quality(sku_rows)["usability"],
            }
        )
    return result


def assert_acceptance(after, comparisons, run_results) -> None:
    for category, capture in after.items():
        compact = compact_capture(capture)
        quant_count = compact["table_counts"][entities.Core3SkuClaimValueQuantification.__tablename__]
        if not quant_count:
            raise RuntimeError(f"{category} M12C draft produced no quantification rows")
        if compact["quality_assessment_row_count"] != quant_count:
            raise RuntimeError(f"{category} M12C quality assessment coverage is incomplete")
        if compact["non_quantifiable_nonzero_row_count"]:
            raise RuntimeError(f"{category} M12C emitted non-zero values for non-quantifiable rows")
        if comparisons[category]["unexpected_profile_review_count"]:
            raise RuntimeError(f"{category} claim-local limitations spread to profile review")
        if Decimal(comparisons[category]["new_missing_rate"]) > Decimal("0.05"):
            raise RuntimeError(f"{category} new missing coverage exceeds 5 percent")
        if not run_results.get(category):
            raise RuntimeError(f"{category} M12C draft run receipt is missing")
        if any(item["status"] != "success" for item in run_results.get(category, ())):
            raise RuntimeError(f"{category} M12C draft run did not finish as success")
        if any(item["warnings"] or item["review_issue_count"] for item in run_results.get(category, ())):
            raise RuntimeError(f"{category} scoped pool issues leaked to module-level review")


def capture_downstream_guard(db) -> dict[str, dict[str, Any]]:
    result = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table_name}")
        ).one()
        result[table_name] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def group_by_sku(rows: Sequence[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        result[str(row.sku_code)].append(row)
    return dict(result)


def is_amount_limited(row: Any) -> bool:
    assessment = (row.supporting_dimensions_json or {}).get("quality_assessment", {})
    if assessment:
        return assessment.get("amount_quantification_status") != "ready"
    return bool(set(row.quality_flags_json or ()) & M12C_AMOUNT_LIMITATION_FLAGS)


def is_relative_limited(row: Any) -> bool:
    assessment = (row.supporting_dimensions_json or {}).get("quality_assessment", {})
    if assessment:
        return assessment.get("relative_comparison_status") == "limited"
    return bool(set(row.quality_flags_json or ()) & M12C_RELATIVE_COMPARISON_LIMITATION_FLAGS)


def has_nonzero_amount(row: Any) -> bool:
    return any(
        Decimal(str(value or 0)) != 0
        for value in (
            row.estimated_price_premium_abs,
            row.estimated_weekly_sales_lift_abs,
            row.estimated_weekly_sales_amount_lift_abs,
        )
    )


def row_key(row: Any) -> tuple[str, str, str, str, str, str]:
    return (
        row.batch_id,
        row.sku_code,
        row.claim_code,
        row.context_type,
        row.context_code,
        row.price_band_group,
    )


def digest_rows(rows: Sequence[Any]) -> str:
    values = [
        (row_key(row), tuple(normalize(getattr(row, field)) for field in QUANT_BUSINESS_FIELDS))
        for row in rows
    ]
    return digest_values(values)


def digest_values(values: Iterable[Any]) -> str:
    encoded = json.dumps(sorted(values), ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-09 TV/AC M12C 草稿验证",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 范围：只修改 M12C 卖点价值与量化限制的作用域，不发布 current，不运行 M12D。",
        "- 口径：价值是否成立、相对比较是否充分、是否可量化金额分开判断。",
        "- 硬门槛：不可量化的卖点行，溢价、销量贡献和销额贡献必须全部为 0。",
        "",
        "| 品类 | 市场 SKU | M12C SKU | 缺失 SKU | 旧 flag partial | 新价值判断可用 | 迁移到可用 | 不可量化非零违规 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in ("TV", "AC"):
        before = payload["before"][category]
        after = payload["after"][category]
        compare = payload["comparisons"][category]
        lines.append(
            f"| {category} | {after['market_scope_count']} | {after['sku_count']} | {after['missing_sku_count']} | "
            f"{before['legacy_status_counts']['partial']} | {after['claim_scoped_status_counts']['usable']} | "
            f"{compare['flag_only_partial_to_usable_count']} | {after['non_quantifiable_nonzero_row_count']} |"
        )
        lines.append(
            f"| {category} 覆盖迁移 | 旧有减少 {compare['coverage_lost_count']} | 新增 {compare['coverage_gained_count']} | "
            f"净变化 {compare['net_coverage_change']} | - | - | - | - |"
        )
    lines.extend(
        [
            "",
            "## 验收",
            "",
            f"- M12D 表未变化：`{payload['downstream_guard']['unchanged']}`",
            "- TV/AC 使用独立 M12C 规则版本和各自上游 taxonomy/市场池。",
            "- 样本不足复核保留在 claim × battlefield × pool，不生成模块级人工复核。",
            "- 当前版本与草稿的卖点角色/证据变化单独记录为上游 QF 草稿输入影响。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-draft", action="store_true")
    parser.add_argument(
        "--output-json",
        default="docs/core3_mvp/real_data_v2/current_implementation/M12D_QF09_tv_ac_m12c_draft.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="docs/core3_mvp/real_data_v2/current_implementation/M12D_QF09_tv_ac_m12c_draft_report.md",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
