"""Read-only 205 feasibility probe for competitor-profile V1.

The script is streamed to the API container through stdin.  It prints one
canonical JSON document and never writes database or remote filesystem state.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from statistics import mean, median
from typing import Any, Iterable

from sqlalchemy import text

from app.core.database import SessionLocal


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CONFIG = {
    "TV": {
        "sku_prefix": "TV",
        "M03B": "m03b_tv_param_profile_v0.2",
        "M04C": "m04c_tv_claim_fact_profile_v0.2",
        "M05C": "m05c_tv_comment_fact_profile_v0.2",
        "M09C": "m09c_tv_user_task_profile_v0.3",
        "M10C": "m10c_tv_target_group_profile_v0.3",
        "M11C": "m11c_tv_value_battlefield_profile_v0.4",
        "M12C": "m12c_tv_claim_value_quantification_v0.2",
    },
    "AC": {
        "sku_prefix": "AC",
        "M03B": "m03b_ac_param_profile_v0.2",
        "M04C": "m04c_ac_claim_fact_profile_v0.2",
        "M05C": "m05c_ac_comment_fact_profile_v0.2",
        "M09C": "m09c_ac_user_task_profile_v0.3",
        "M10C": "m10c_ac_target_group_profile_v0.3",
        "M11C": "m11c_ac_value_battlefield_profile_v0.3",
        "M12C": "m12c_ac_claim_value_quantification_v0.2",
    },
}
M07_RULE = "m07_market_profile_v2"
M11D_RULE = "m11d_semantic_market_allocation_v0.1"
M12D_RULE = "m12d_sku_purchase_reason_profile_v0.1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _rows(db: Any, sql: str, **params: Any) -> list[dict[str, Any]]:
    values = {"project_id": PROJECT_ID, **params}
    return [dict(row._mapping) for row in db.execute(text(sql), values)]


def _sku_set(rows: Iterable[dict[str, Any]]) -> set[str]:
    return {str(row["sku_code"]) for row in rows if row.get("sku_code")}


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _weekly_volume(row: dict[str, Any]) -> float | None:
    volume = _positive_number(row.get("sales_volume_total"))
    weeks = _positive_number(row.get("active_week_count"))
    return volume / weeks if volume is not None and weeks is not None else None


def _price_near(target: dict[str, Any], candidate: dict[str, Any], ratio: float) -> bool:
    target_price = _positive_number(target.get("price_wavg"))
    candidate_price = _positive_number(candidate.get("price_wavg"))
    return bool(
        target_price is not None
        and candidate_price is not None
        and abs(candidate_price / target_price - 1) <= ratio
    )


def _same_product_form(
    category: str,
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if category == "TV":
        return (
            target.get("screen_size_inch") is not None
            and target.get("screen_size_inch") == candidate.get("screen_size_inch")
        )
    return bool(
        target.get("market_pool_key")
        and target.get("market_pool_key") == candidate.get("market_pool_key")
    )


def _shared_semantic(
    target_sku: str,
    candidate_sku: str,
    task_by_sku: dict[str, str],
    group_by_sku: dict[str, str],
    battlefield_by_sku: dict[str, str],
    anchors_by_sku: dict[str, set[str]],
) -> bool:
    return any(
        (
            left.get(target_sku)
            and left.get(target_sku) == left.get(candidate_sku)
        )
        for left in (task_by_sku, group_by_sku, battlefield_by_sku)
    ) or bool(anchors_by_sku.get(target_sku, set()) & anchors_by_sku.get(candidate_sku, set()))


def _distribution(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"min": 0, "p50": 0, "p90": 0, "max": 0, "mean": 0.0}
    p90_index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * 0.9)))
    return {
        "min": ordered[0],
        "p50": median(ordered),
        "p90": ordered[p90_index],
        "max": ordered[-1],
        "mean": round(mean(ordered), 4),
    }


def _module_coverage(
    base_skus: set[str],
    module_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for module, rows in module_rows.items():
        covered = base_skus & _sku_set(rows)
        missing = sorted(base_skus - covered)
        result[module] = {
            "covered_skus": len(covered),
            "missing_skus": len(missing),
            "coverage_rate": round(len(covered) / len(base_skus), 6) if base_skus else 0,
            "missing_sample": missing[:10],
        }
    return result


def _category_snapshot(db: Any, category: str) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    market_rows = _rows(
        db,
        """
        SELECT sku_code, model_name, brand_name, batch_id, market_pool_key,
               screen_size_inch, size_segment, price_band_size, price_wavg,
               sales_volume_total, sales_amount_total, active_week_count, result_hash
          FROM core3_sku_market_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version
           AND analysis_window='full_observed_window' AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=M07_RULE,
    )
    param_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, profile_hash
          FROM core3_sku_param_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M03B"],
    )
    claim_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, profile_hash
          FROM core3_sku_claim_fact_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M04C"],
    )
    comment_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, profile_hash
          FROM core3_sku_comment_fact_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M05C"],
    )
    task_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, primary_user_task_code, profile_hash
          FROM core3_m09c_sku_user_task_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M09C"],
    )
    group_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, primary_target_group_code, profile_hash
          FROM core3_m10c_sku_target_group_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M10C"],
    )
    battlefield_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, primary_battlefield_code, profile_hash
          FROM core3_sku_value_battlefield_profile
         WHERE project_id=:project_id AND category_code=:category
           AND rule_version=:rule_version AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M11C"],
    )
    m11d_rows = _rows(
        db,
        """
        SELECT DISTINCT sku_code, batch_id
          FROM core3_semantic_market_sku_contribution
         WHERE project_id=:project_id AND category_code=:category
           AND product_category=:category AND rule_version=:rule_version
           AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=M11D_RULE,
    )
    m12c_rows = _rows(
        db,
        """
        SELECT DISTINCT sku_code, batch_id
          FROM core3_sku_claim_value_quantification
         WHERE project_id=:project_id AND category_code=:category
           AND product_category=:category AND rule_version=:rule_version
           AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=config["M12C"],
    )
    m12d_rows = _rows(
        db,
        """
        SELECT sku_code, batch_id, status, profile_confidence, core_payment_anchors_json,
               established_anchors_json, release_status, result_hash
          FROM core3_sku_purchase_reason_profile
         WHERE project_id=:project_id AND category_code=:category
           AND product_category=:category AND rule_version=:rule_version
           AND release_status='published' AND is_current=true
         ORDER BY sku_code
        """,
        category=category,
        rule_version=M12D_RULE,
    )
    anchor_rows = _rows(
        db,
        """
        SELECT sku_code, anchor_code, role, establishment_status, core_eligible
          FROM core3_sku_purchase_reason_anchor
         WHERE project_id=:project_id AND category_code=:category
           AND product_category=:category AND rule_version=:rule_version
           AND release_status='published' AND is_current=true
           AND establishment_status IN ('established','established_limited')
           AND (role='core_payment' OR core_eligible=true)
         ORDER BY sku_code, anchor_code
        """,
        category=category,
        rule_version=M12D_RULE,
    )
    version_rows = _rows(
        db,
        """
        SELECT m12d_profile_version, release_status, release_quality_status,
               sku_count, ready_count, review_required_count, missing_input_count,
               failed_count, source_batch_ids_json, published_at
          FROM core3_purchase_reason_profile_version
         WHERE project_id=:project_id AND category_code=:category
           AND release_status='published' AND is_current=true
        """,
        category=category,
    )

    modules = {
        "M03B": param_rows,
        "M04C": claim_rows,
        "M05C": comment_rows,
        "M07": market_rows,
        "M09C": task_rows,
        "M10C": group_rows,
        "M11C": battlefield_rows,
        "M11D": m11d_rows,
        "M12C": m12c_rows,
        "M12D": m12d_rows,
    }
    markets = {row["sku_code"]: row for row in market_rows}
    base_skus = set(markets)
    task_by_sku = {
        row["sku_code"]: row["primary_user_task_code"]
        for row in task_rows
        if row.get("primary_user_task_code")
    }
    group_by_sku = {
        row["sku_code"]: row["primary_target_group_code"]
        for row in group_rows
        if row.get("primary_target_group_code")
    }
    battlefield_by_sku = {
        row["sku_code"]: row["primary_battlefield_code"]
        for row in battlefield_rows
        if row.get("primary_battlefield_code")
    }
    anchors_by_sku: dict[str, set[str]] = defaultdict(set)
    for row in anchor_rows:
        if row.get("anchor_code"):
            anchors_by_sku[row["sku_code"]].add(row["anchor_code"])

    source_target_counts = Counter()
    source_pair_counts = Counter()
    union_counts: dict[str, int] = {}
    source_counts_by_sku: dict[str, dict[str, int]] = {}
    for target_sku, target in markets.items():
        sources: dict[str, set[str]] = defaultdict(set)
        for candidate_sku, candidate in markets.items():
            if candidate_sku == target_sku:
                continue
            if (
                target.get("market_pool_key")
                and target.get("market_pool_key") == candidate.get("market_pool_key")
            ):
                sources["same_market_pool"].add(candidate_sku)
            if _same_product_form(category, target, candidate) and _price_near(target, candidate, 0.15):
                sources["same_product_form_budget"].add(candidate_sku)
            if (
                target.get("brand_name")
                and target.get("brand_name") == candidate.get("brand_name")
            ):
                sources["same_brand_ladder"].add(candidate_sku)
            if task_by_sku.get(target_sku) and task_by_sku.get(target_sku) == task_by_sku.get(candidate_sku):
                sources["same_primary_task"].add(candidate_sku)
            if group_by_sku.get(target_sku) and group_by_sku.get(target_sku) == group_by_sku.get(candidate_sku):
                sources["same_primary_group"].add(candidate_sku)
            if (
                battlefield_by_sku.get(target_sku)
                and battlefield_by_sku.get(target_sku) == battlefield_by_sku.get(candidate_sku)
            ):
                sources["same_primary_battlefield"].add(candidate_sku)
            if anchors_by_sku.get(target_sku, set()) & anchors_by_sku.get(candidate_sku, set()):
                sources["shared_core_anchor"].add(candidate_sku)

            target_price = _positive_number(target.get("price_wavg"))
            candidate_price = _positive_number(candidate.get("price_wavg"))
            target_weekly = _weekly_volume(target)
            candidate_weekly = _weekly_volume(candidate)
            shared = _shared_semantic(
                target_sku,
                candidate_sku,
                task_by_sku,
                group_by_sku,
                battlefield_by_sku,
                anchors_by_sku,
            )
            if (
                shared
                and target_price is not None
                and candidate_price is not None
                and candidate_price <= target_price * 0.85
                and target_weekly is not None
                and candidate_weekly is not None
                and candidate_weekly > target_weekly
            ):
                sources["downtrade_price_volume"].add(candidate_sku)
            if (
                shared
                and target_price is not None
                and candidate_price is not None
                and candidate_price >= target_price * 1.15
            ):
                sources["uptrade_shared_value"].add(candidate_sku)

        union = set().union(*sources.values()) if sources else set()
        union_counts[target_sku] = len(union)
        source_counts_by_sku[target_sku] = {
            source: len(candidates) for source, candidates in sorted(sources.items())
        }
        for source, candidates in sources.items():
            if candidates:
                source_target_counts[source] += 1
                source_pair_counts[source] += len(candidates)

    status_counts = Counter(str(row.get("status") or "unknown") for row in m12d_rows)
    sku_prefix_mismatches = sorted(
        sku for sku in base_skus if not sku.startswith(str(config["sku_prefix"]))
    )
    richest = max(union_counts, key=lambda sku: (union_counts[sku], sku)) if union_counts else None
    fixed_sample = "TV00029112" if category == "TV" and "TV00029112" in base_skus else richest
    return {
        "category_code": category,
        "base_sku_count": len(base_skus),
        "rules": {
            **{module: config[module] for module in ("M03B", "M04C", "M05C", "M09C", "M10C", "M11C", "M12C")},
            "M07": M07_RULE,
            "M11D": M11D_RULE,
            "M12D": M12D_RULE,
        },
        "source_batches": {
            module: sorted({str(row["batch_id"]) for row in rows if row.get("batch_id")})
            for module, rows in modules.items()
        },
        "module_coverage": _module_coverage(base_skus, modules),
        "m12d_current_version": version_rows,
        "m12d_status_counts": dict(sorted(status_counts.items())),
        "m12d_skus_with_established_core_anchor": len(set(anchors_by_sku) & base_skus),
        "candidate_source_target_coverage": dict(sorted(source_target_counts.items())),
        "candidate_source_pair_counts": dict(sorted(source_pair_counts.items())),
        "broad_union": {
            "targets_with_at_least_1": sum(value >= 1 for value in union_counts.values()),
            "targets_with_at_least_5": sum(value >= 5 for value in union_counts.values()),
            "targets_with_at_least_20": sum(value >= 20 for value in union_counts.values()),
            "candidate_count_distribution": _distribution(list(union_counts.values())),
        },
        "sample_target": {
            "sku_code": fixed_sample,
            "candidate_source_counts": source_counts_by_sku.get(fixed_sample or "", {}),
            "broad_union_count": union_counts.get(fixed_sample or "", 0),
        },
        "richest_target": {
            "sku_code": richest,
            "candidate_source_counts": source_counts_by_sku.get(richest or "", {}),
            "broad_union_count": union_counts.get(richest or "", 0),
        },
        "sku_prefix_mismatch_count": len(sku_prefix_mismatches),
        "sku_prefix_mismatch_sample": sku_prefix_mismatches[:10],
    }


def _isolation_snapshot(db: Any) -> dict[str, Any]:
    tables = {
        "M04C": "core3_sku_claim_fact_profile",
        "M05C": "core3_sku_comment_fact_profile",
        "M09C": "core3_m09c_sku_user_task_profile",
        "M10C": "core3_m10c_sku_target_group_profile",
        "M11C": "core3_sku_value_battlefield_profile",
        "M11D": "core3_semantic_market_sku_contribution",
        "M12C": "core3_sku_claim_value_quantification",
        "M12D": "core3_sku_purchase_reason_profile",
    }
    result: dict[str, Any] = {}
    for module, table_name in tables.items():
        rows = _rows(
            db,
            f"""
            SELECT count(*) AS mismatch_rows, count(DISTINCT sku_code) AS mismatch_skus
              FROM {table_name}
             WHERE project_id=:project_id AND category_code IN ('TV','AC')
               AND product_category <> category_code
            """,
        )
        result[module] = rows[0]
    result["M03B_wrong_rule_under_category"] = _rows(
        db,
        """
        SELECT category_code, rule_version, count(*) AS rows,
               count(DISTINCT sku_code) AS skus
          FROM core3_sku_param_profile
         WHERE project_id=:project_id
           AND ((category_code='TV' AND rule_version LIKE 'm03b_ac_%')
             OR (category_code='AC' AND rule_version LIKE 'm03b_tv_%'))
         GROUP BY category_code, rule_version
         ORDER BY category_code, rule_version
        """,
    )
    return result


def main() -> None:
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        payload = {
            "schema_version": "competitor_profile_g02_probe_v1",
            "project_id": PROJECT_ID,
            "categories": {
                category: _category_snapshot(db, category)
                for category in ("TV", "AC")
            },
            "category_isolation": _isolation_snapshot(db),
        }
        db.rollback()

    canonical = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["snapshot_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    print(json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
