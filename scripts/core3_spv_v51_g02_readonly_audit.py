"""Read-only 205 baseline audit for the sellpoint-value V5.1 migration.

Run this module inside the CatForge API container.  It performs only SELECTs and
prints one deterministic JSON document; it never commits or mutates ORM rows.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import bindparam, select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_METHOD_VERSION,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext


TARGET_SKU_CODE = "TV00029112"
SPV_METHOD_VERSION = "sellpoint_value_pm_v5_profile_v1"


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _sorted_counter(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _reason_values(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        values = payload.get("reasons", [])
    else:
        values = payload or []
    return [str(value) for value in values if value]


def _latest_spv_versions(db) -> dict[str, entities.Core3SellpointValueProfileVersion]:
    rows = db.scalars(
        select(entities.Core3SellpointValueProfileVersion)
        .where(
            entities.Core3SellpointValueProfileVersion.method_version
            == SPV_METHOD_VERSION
        )
        .order_by(entities.Core3SellpointValueProfileVersion.generated_at.desc())
    ).all()
    latest: dict[str, entities.Core3SellpointValueProfileVersion] = {}
    for row in rows:
        latest.setdefault(row.category_code, row)
    if set(latest) != {"TV", "AC"}:
        raise RuntimeError("latest V5 baseline must contain both TV and AC")
    return latest


def _spv_baseline(db, versions) -> dict[str, Any]:
    version_ids = [row.sellpoint_value_profile_version_id for row in versions.values()]
    version_query_params = {"version_ids": version_ids}
    version_ids_param = bindparam("version_ids", expanding=True)

    distribution_rows = db.execute(
        text(
            """
            select category_code, analysis_state, review_required, count(*) as row_count
            from core3_sku_sellpoint_value_profile
            where sellpoint_value_profile_version_id in :version_ids
            group by category_code, analysis_state, review_required
            order by category_code, analysis_state, review_required
            """
        ).bindparams(version_ids_param),
        version_query_params,
    ).mappings().all()
    profile_distribution = {"TV": {}, "AC": {}}
    for row in distribution_rows:
        key = f"{row.analysis_state}|review={str(row.review_required).lower()}"
        profile_distribution[row.category_code][key] = int(row.row_count)

    reason_rows = db.execute(
        text(
            """
            select p.category_code, reason, count(*) as row_count
            from core3_sku_sellpoint_value_profile p
            cross join lateral jsonb_array_elements_text(
              coalesce(p.review_reason_json->'reasons', '[]'::jsonb)
            ) reason
            where p.sellpoint_value_profile_version_id in :version_ids
            group by p.category_code, reason
            order by p.category_code, reason
            """
        ).bindparams(version_ids_param),
        version_query_params,
    ).mappings().all()
    profile_review_reasons = {"TV": {}, "AC": {}}
    for row in reason_rows:
        profile_review_reasons[row.category_code][row.reason] = int(row.row_count)

    classification_rows = db.execute(
        text(
            """
            select p.category_code,
                   coalesce(decision->>'classification', 'unknown') as classification,
                   count(*) as row_count
            from core3_sku_sellpoint_value_profile p
            cross join lateral jsonb_array_elements(p.investment_decisions_json) decision
            where p.sellpoint_value_profile_version_id in :version_ids
            group by p.category_code, classification
            order by p.category_code, classification
            """
        ).bindparams(version_ids_param),
        version_query_params,
    ).mappings().all()
    investment_classifications = {"TV": {}, "AC": {}}
    for row in classification_rows:
        investment_classifications[row.category_code][row.classification] = int(
            row.row_count
        )

    investment_reason_rows = db.execute(
        text(
            """
            select p.category_code, reason, count(*) as row_count
            from core3_sku_sellpoint_value_profile p
            cross join lateral jsonb_array_elements(p.investment_decisions_json) decision
            cross join lateral jsonb_array_elements_text(
              coalesce(decision->'review_reasons', '[]'::jsonb)
            ) reason
            where p.sellpoint_value_profile_version_id in :version_ids
            group by p.category_code, reason
            order by p.category_code, reason
            """
        ).bindparams(version_ids_param),
        version_query_params,
    ).mappings().all()
    investment_review_reasons = {"TV": {}, "AC": {}}
    for row in investment_reason_rows:
        investment_review_reasons[row.category_code][row.reason] = int(row.row_count)

    item_rows = db.execute(
        text(
            """
            select category_code,
                   count(*) as total,
                   count(*) filter (where review_required) as review_required,
                   count(*) filter (
                     where jsonb_array_length(
                       coalesce(price_realization_json->'direct_and_pool_gaps', '[]'::jsonb)
                     ) > 0
                   ) as direct_market_gap_available,
                   count(*) filter (
                     where price_realization_json->'strict_bundle_interval'->>'status' = 'available'
                   ) as strict_market_implied_wtp_available
            from core3_sku_sellpoint_value_item
            where sellpoint_value_profile_version_id in :version_ids
            group by category_code
            order by category_code
            """
        ).bindparams(version_ids_param),
        version_query_params,
    ).mappings().all()
    item_summary = {
        row.category_code: {
            "total": int(row.total),
            "review_required": int(row.review_required),
            "direct_market_gap_available": int(row.direct_market_gap_available),
            "strict_market_implied_wtp_available": int(
                row.strict_market_implied_wtp_available
            ),
        }
        for row in item_rows
    }

    target_profile = db.execute(
        select(
            entities.Core3SkuSellpointValueProfile.sku_sellpoint_value_profile_id,
            entities.Core3SkuSellpointValueProfile.analysis_state,
            entities.Core3SkuSellpointValueProfile.profile_confidence,
            entities.Core3SkuSellpointValueProfile.review_required,
            entities.Core3SkuSellpointValueProfile.review_reason_json,
            entities.Core3SkuSellpointValueProfile.candidate_universe_summary_json,
        ).where(
            entities.Core3SkuSellpointValueProfile.sellpoint_value_profile_version_id
            == versions["TV"].sellpoint_value_profile_version_id,
            entities.Core3SkuSellpointValueProfile.sku_code == TARGET_SKU_CODE,
        )
    ).mappings().one()
    target_items = db.execute(
        select(
            entities.Core3SkuSellpointValueItem.normalized_bundle_code,
            entities.Core3SkuSellpointValueItem.value_bundle_name_cn,
            entities.Core3SkuSellpointValueItem.perceived_value_status,
            entities.Core3SkuSellpointValueItem.price_realization_json,
            entities.Core3SkuSellpointValueItem.review_required,
            entities.Core3SkuSellpointValueItem.review_reason_json,
        ).where(
            entities.Core3SkuSellpointValueItem.sellpoint_value_profile_version_id
            == versions["TV"].sellpoint_value_profile_version_id,
            entities.Core3SkuSellpointValueItem.sku_code == TARGET_SKU_CODE,
        )
    ).mappings().all()
    target_candidates = db.execute(
        select(
            entities.Core3SkuSellpointValueCandidate.pool_type,
            entities.Core3SkuSellpointValueCandidate.eligibility_status,
        ).where(
            entities.Core3SkuSellpointValueCandidate.sku_sellpoint_value_profile_id
            == target_profile.sku_sellpoint_value_profile_id
        )
    ).all()

    item_rows = []
    for item in sorted(target_items, key=lambda row: row.normalized_bundle_code):
        price = item.price_realization_json or {}
        gaps = price.get("direct_and_pool_gaps") or []
        item_rows.append(
            {
                "normalized_bundle_code": item.normalized_bundle_code,
                "value_bundle_name_cn": item.value_bundle_name_cn,
                "perceived_value_status": item.perceived_value_status,
                "review_required": item.review_required,
                "review_reasons": _reason_values(item.review_reason_json),
                "direct_market_gaps": [
                    {
                        "method": gap.get("method"),
                        "comparator_count": gap.get("comparator_count"),
                        "comparator_sku_codes": gap.get("comparator_sku_codes", []),
                        "price_gap_abs": gap.get("price_gap_abs"),
                        "price_gap_pct": gap.get("price_gap_pct"),
                        "sales_volume_gap_abs": gap.get("sales_volume_gap_abs"),
                        "sales_volume_gap_pct": gap.get("sales_volume_gap_pct"),
                        "causal_claim": gap.get("causal_claim"),
                    }
                    for gap in gaps
                ],
                "strict_wtp_status": (
                    price.get("strict_bundle_interval") or {}
                ).get("status"),
            }
        )

    return {
        "versions": {
            category: {
                "version_id": row.sellpoint_value_profile_version_id,
                "profile_version": row.profile_version,
                "release_status": row.release_status,
                "release_quality_status": row.release_quality_status,
                "is_current": row.is_current,
                "sku_count": row.sku_count,
                "ready_count": row.ready_count,
                "review_required_count": row.review_required_count,
                "blocked_count": row.blocked_count,
                "failed_count": row.failed_count,
                "result_hash": row.result_hash,
            }
            for category, row in sorted(versions.items())
        },
        "profile_distribution": profile_distribution,
        "profile_review_reasons": profile_review_reasons,
        "investment_classifications": investment_classifications,
        "investment_review_reasons": investment_review_reasons,
        "value_item_summary": item_summary,
        "target_65e7q": {
            "profile_id": target_profile.sku_sellpoint_value_profile_id,
            "analysis_state": target_profile.analysis_state,
            "profile_confidence": target_profile.profile_confidence,
            "review_required": target_profile.review_required,
            "review_reasons": _reason_values(target_profile.review_reason_json),
            "candidate_universe": target_profile.candidate_universe_summary_json,
            "candidate_pool_counts": _sorted_counter(
                row.pool_type for row in target_candidates
            ),
            "candidate_status_counts": _sorted_counter(
                row.eligibility_status for row in target_candidates
            ),
            "value_items": item_rows,
        },
    }


def _competitor_profile_baseline(db) -> dict[str, Any]:
    versions = db.scalars(
        select(entities.Core3CompetitorProfileVersion)
        .where(
            entities.Core3CompetitorProfileVersion.method_version
            == AGENT_SNAPSHOT_METHOD_VERSION,
            entities.Core3CompetitorProfileVersion.release_status == "published",
            entities.Core3CompetitorProfileVersion.is_current.is_(True),
        )
        .order_by(entities.Core3CompetitorProfileVersion.category_code)
    ).all()
    if {row.category_code for row in versions} != {"TV", "AC"}:
        raise RuntimeError("current competitor profiles must contain TV and AC")

    tv_version = next(row for row in versions if row.category_code == "TV")
    repository = CompetitorProfileAgentSnapshotRepository(
        Core3RepositoryContext(
            db=db,
            project_id=tv_version.project_id,
            category_code=Core3CategoryCode.TV,
        )
    )
    target = repository.read_agent_snapshot(
        target_sku_code=TARGET_SKU_CODE,
        read_mode="compact",
        access_mode="formal",
    )
    if target.status != "available" or target.compact is None:
        raise RuntimeError("65E7Q formal competitor profile is unavailable")
    compact = target.compact
    return {
        "versions": {
            row.category_code: {
                "version_id": row.competitor_profile_version_id,
                "profile_version": row.profile_version,
                "release_status": row.release_status,
                "release_quality_status": row.release_quality_status,
                "is_current": row.is_current,
                "sku_count": row.sku_count,
                "pair_count": row.pair_count,
                "selection_count": row.selection_count,
                "result_hash": row.result_hash,
            }
            for row in versions
        },
        "target_65e7q": {
            "version_id": target.competitor_profile_version_id,
            "candidate_count": compact.candidate_count,
            "priority_order": compact.priority_order,
            "candidates": [
                {
                    "sku_code": row.candidate_sku_code,
                    "source_rank": row.source_rank,
                    "selected_rank": row.selected_rank,
                    "role": row.role,
                    "business_score": row.business_score,
                    "result_hash": row.result_hash,
                }
                for row in compact.pair_index
            ],
            "source_result_hash": compact.profile_result_hash,
        },
    }


def main() -> None:
    with SessionLocal() as db:
        versions = _latest_spv_versions(db)
        result = {
            "audit_contract": "spv_v5_1_g02_readonly_baseline_v1",
            "target_sku_code": TARGET_SKU_CODE,
            "spv_v5": _spv_baseline(db, versions),
            "competitor_profile": _competitor_profile_baseline(db),
            "forbidden_formal_candidate_sources": [
                "sellpoint_value_candidate_universe",
                "M12 candidate recall",
                "M13 candidate scoring",
                "M14 priority selection",
                "live competitor-set analysis",
            ],
        }
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=_json_default,
            )
        )
        db.rollback()


if __name__ == "__main__":
    main()
