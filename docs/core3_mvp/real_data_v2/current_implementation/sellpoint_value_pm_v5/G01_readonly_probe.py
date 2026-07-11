"""V5-G01 read-only feasibility probe for the 205 CatForge TV dataset.

The script is streamed to ``docker exec ... python -`` and writes only a
canonical JSON object to stdout.  It never persists database or filesystem
state on the target host.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CODE = "TV"
ALL_TV_BATTLEFIELDS = {
    "BF_SMALL_SCREEN_ESSENTIAL_VALUE",
    "BF_SMALL_SMART_EASY_USE",
    "BF_MAINSTREAM_FAMILY_VALUE",
    "BF_MAINSTREAM_LIVING_BALANCE",
    "BF_LARGE_SCREEN_VALUE_UPGRADE",
    "BF_LARGE_SCREEN_FAMILY_CINEMA",
    "BF_PREMIUM_PICTURE_UPGRADE",
    "BF_PREMIUM_VALUE_DOWNTRADE",
    "BF_GAMING_SPORTS_FLUENCY",
    "BF_EYE_CARE_FAMILY_COMFORT",
    "BF_SMART_CONNECTED_EXPERIENCE",
    "BF_GIANT_SCREEN_VALUE_DOWNTRADE",
    "BF_GIANT_HOME_THEATER_FLAGSHIP",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _rows(db: Any, sql: str) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in db.execute(text(sql), {"project_id": PROJECT_ID})]


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _entered_battlefields(profile: dict[str, Any] | None) -> set[str]:
    if not profile:
        return set()
    result = {profile["primary_battlefield_code"]} if profile.get("primary_battlefield_code") else set()
    result.update(profile.get("secondary_battlefield_codes_json") or [])
    result.update(profile.get("opportunity_battlefield_codes_json") or [])
    summary = profile.get("battlefield_summary_json") or {}
    for row in summary.get("opportunity") or []:
        if row.get("relation_status") == "user_observed_battlefield" and row.get("battlefield_code"):
            result.add(row["battlefield_code"])
    return result


def _observable_reachable_excluded(profile: dict[str, Any] | None) -> set[str]:
    if not profile:
        return set()
    summary = profile.get("battlefield_summary_json") or {}
    entered = _entered_battlefields(profile)
    param_strong = set((summary.get("claim_param_summary") or {}).get("param_strong_battlefield_codes") or [])
    top_voice = summary.get("user_voice_summary", {}).get("top_user_voice") or []
    return {
        row["battlefield_code"]
        for row in top_voice
        if row.get("relation_status") == "excluded"
        and row.get("battlefield_code") in param_strong
        and float(row.get("battlefield_score") or 0) >= 0.55
        and row.get("battlefield_code") not in entered
    }


def _price_near(target: dict[str, Any], candidate: dict[str, Any], ratio: float) -> bool:
    target_price = float(target.get("price_wavg") or 0)
    candidate_price = float(candidate.get("price_wavg") or 0)
    return target_price > 0 and candidate_price > 0 and abs(candidate_price / target_price - 1) <= ratio


def main() -> None:
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))

        market_rows = _rows(
            db,
            """
            SELECT sku_code, model_name, brand_name, batch_id, screen_size_inch,
                   size_segment, market_pool_key, price_wavg, sales_volume_total,
                   sales_amount_total, active_week_count, platform_count,
                   price_min, price_max, price_volatility,
                   same_pool_price_percentile, same_pool_volume_percentile,
                   same_pool_amount_percentile, promotion_suspect_flag,
                   result_hash
              FROM core3_sku_market_profile
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m07_market_profile_v2'
               AND analysis_window='full_observed_window' AND is_current=true
             ORDER BY sku_code
            """,
        )
        m11c_rows = _rows(
            db,
            """
            SELECT sku_code, model_name, brand_name, batch_id, primary_battlefield_code,
                   secondary_battlefield_codes_json, opportunity_battlefield_codes_json,
                   drag_factor_battlefield_codes_json, battlefield_summary_json,
                   profile_hash
              FROM core3_sku_value_battlefield_profile
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m11c_tv_value_battlefield_profile_v0.4'
               AND is_current=true
             ORDER BY sku_code
            """,
        )
        tier_rows = _rows(
            db,
            """
            SELECT sku_code, dimension_code, tier_code, tier_rank, profile_hash
              FROM core3_sku_param_dimension_tier
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m03b_tv_param_profile_v0.2' AND is_current=true
             ORDER BY sku_code, dimension_code
            """,
        )
        param_rows = _rows(
            db,
            """
            SELECT sku_code, model_name, batch_id, param_values_json,
                   core_picture_params_json, core_gaming_params_json,
                   core_system_params_json, core_eye_care_params_json,
                   conflict_count, profile_hash
              FROM core3_sku_param_profile
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m03b_tv_param_profile_v0.2'
             ORDER BY sku_code
            """,
        )
        claim_rows = _rows(
            db,
            """
            SELECT sku_code, claim_codes, fact_claim_codes, profile_hash
              FROM core3_sku_claim_fact_profile
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m04c_tv_claim_fact_profile_v0.2' AND is_current=true
             ORDER BY sku_code
            """,
        )
        comment_rows = _rows(
            db,
            """
            SELECT sku_code, supported_claim_codes, contradicted_claim_codes,
                   unmentioned_claim_codes, comment_sentence_count,
                   positive_sentence_count, negative_sentence_count, profile_hash
              FROM core3_sku_comment_fact_profile
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m05c_tv_comment_fact_profile_v0.2' AND is_current=true
             ORDER BY sku_code
            """,
        )
        m12d_rows = _rows(
            db,
            """
            SELECT sku_code, batch_id, status, release_status, source_refs_json, result_hash
              FROM core3_sku_purchase_reason_profile
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='m12d_sku_purchase_reason_profile_v0.1' AND is_current=true
             ORDER BY sku_code
            """,
        )
        m11d_rows = _rows(
            db,
            """
            SELECT sku_code, batch_id, dimension_code, allocation_weight,
                   allocated_sales_volume, allocated_sales_amount, result_hash
              FROM core3_semantic_market_sku_contribution
             WHERE project_id=:project_id AND category_code='TV'
               AND product_category='TV' AND dimension_type='battlefield'
               AND rule_version='m11d_semantic_market_allocation_v0.1'
               AND is_current=true
             ORDER BY sku_code, dimension_code
            """,
        )
        m14_summary = _rows(
            db,
            """
            SELECT count(*) AS raw_runs,
                   count(*) FILTER (
                     WHERE processing_status='success'
                       AND review_required=false
                       AND review_status IN ('auto_pass','approved')
                   ) AS eligible_runs,
                   count(DISTINCT target_sku_code) AS raw_target_skus,
                   coalesce(sum(selected_count),0) AS raw_selected_slots,
                   array_agg(DISTINCT batch_id ORDER BY batch_id) AS batches,
                   array_agg(DISTINCT selection_status ORDER BY selection_status) AS statuses
              FROM core3_competitor_selection_run
             WHERE project_id=:project_id AND category_code='TV'
               AND rule_version='core3_mvp_real_data_v2_m14_v1' AND is_current=true
            """,
        )[0]

        markets = {row["sku_code"]: row for row in market_rows}
        m11c = {row["sku_code"]: row for row in m11c_rows}
        params = {row["sku_code"]: row for row in param_rows}
        claims = {row["sku_code"]: row for row in claim_rows}
        comments = {row["sku_code"]: row for row in comment_rows}
        m12d = {row["sku_code"]: row for row in m12d_rows}
        tiers: dict[str, dict[str, int]] = {}
        for row in tier_rows:
            if row.get("tier_rank") is not None:
                tiers.setdefault(row["sku_code"], {})[row["dimension_code"]] = int(row["tier_rank"])
        entered = {sku: _entered_battlefields(m11c.get(sku)) for sku in markets}

        coverage = Counter()
        peer_counts: dict[str, dict[str, int]] = {}
        param_roles: dict[str, set[str]] = {}
        claim_realization_contrast: dict[str, dict[str, list[str]]] = {}
        synthetic_candidates: list[tuple[int, str]] = []

        for sku, target in markets.items():
            size_peers = [
                row
                for other, row in markets.items()
                if other != sku and row.get("screen_size_inch") == target.get("screen_size_inch")
            ]
            pool_peers = [row for row in size_peers if row.get("market_pool_key") == target.get("market_pool_key")]
            budget_peers = [row for row in size_peers if _price_near(target, row, 0.15)]
            battlefield_budget_peers = [
                row
                for row in budget_peers
                if entered.get(sku) and entered.get(row["sku_code"]) and entered[sku] & entered[row["sku_code"]]
            ]
            primary_budget_peers = [
                row
                for row in budget_peers
                if m11c.get(sku)
                and m11c.get(row["sku_code"])
                and m11c[sku].get("primary_battlefield_code")
                == m11c[row["sku_code"]].get("primary_battlefield_code")
            ]
            same_brand = [row for row in size_peers if row.get("brand_name") == target.get("brand_name")]
            synthetic_pool = [
                row
                for row in size_peers
                if _price_near(target, row, 0.30)
                and entered.get(sku)
                and entered.get(row["sku_code"])
                and entered[sku] & entered[row["sku_code"]]
            ]
            peer_counts[sku] = {
                "market_pool": len(pool_peers),
                "same_budget": len(budget_peers),
                "same_budget_battlefield": len(battlefield_budget_peers),
                "same_budget_primary_battlefield": len(primary_budget_peers),
                "same_brand_size": len(same_brand),
                "synthetic_donor_pool": len(synthetic_pool),
            }
            coverage["market_pool_baseline"] += bool(pool_peers)
            coverage["same_budget"] += bool(budget_peers)
            coverage["same_budget_battlefield"] += bool(battlefield_budget_peers)
            coverage["same_budget_primary_battlefield"] += bool(primary_budget_peers)
            coverage["same_brand_size"] += bool(same_brand)
            coverage["battlefield_peer_ge3"] += len(battlefield_budget_peers) >= 3
            coverage["battlefield_peer_ge5"] += len(battlefield_budget_peers) >= 5
            coverage["primary_battlefield_peer_ge3"] += len(primary_budget_peers) >= 3
            coverage["primary_battlefield_peer_ge5"] += len(primary_budget_peers) >= 5
            coverage["synthetic_donor_ge5"] += len(synthetic_pool) >= 5
            coverage["own_price_curve_strong"] += (
                int(target.get("active_week_count") or 0) >= 8
                and int(target.get("platform_count") or 0) >= 2
                and float(target.get("price_volatility") or 0) > 0
            )
            if len(synthetic_pool) >= 5:
                synthetic_candidates.append((len(synthetic_pool), sku))

            target_tiers = tiers.get(sku, {})
            roles: set[str] = set()
            for peer in budget_peers:
                peer_tiers = tiers.get(peer["sku_code"], {})
                for dimension in target_tiers.keys() & peer_tiers.keys():
                    diff = peer_tiers[dimension] - target_tiers[dimension]
                    roles.add("higher" if diff > 0 else "lower" if diff < 0 else "same")
            if roles:
                coverage["param_tier_comparable"] += 1
                param_roles[sku] = roles

            target_claims = set((claims.get(sku) or {}).get("claim_codes") or [])
            target_supported = set((comments.get(sku) or {}).get("supported_claim_codes") or [])
            advertised_realized = target_claims & target_supported
            if target_claims:
                coverage["advertised_claim"] += 1
            if advertised_realized:
                coverage["advertised_claim_realized"] += 1
            peer_not_realized: set[str] = set()
            peer_contradicted: set[str] = set()
            for peer in budget_peers:
                peer_sku = peer["sku_code"]
                peer_claims = set((claims.get(peer_sku) or {}).get("claim_codes") or [])
                peer_supported = set((comments.get(peer_sku) or {}).get("supported_claim_codes") or [])
                peer_contra = set((comments.get(peer_sku) or {}).get("contradicted_claim_codes") or [])
                same_claims = advertised_realized & peer_claims
                peer_not_realized.update(same_claims - peer_supported)
                peer_contradicted.update(same_claims & peer_contra)
            if peer_not_realized:
                coverage["same_claim_peer_not_realized"] += 1
            if peer_contradicted:
                coverage["same_claim_peer_contradicted"] += 1
            if peer_not_realized or peer_contradicted:
                claim_realization_contrast[sku] = {
                    "peer_not_realized_claim_codes": sorted(peer_not_realized),
                    "peer_contradicted_claim_codes": sorted(peer_contradicted),
                }

        role_counts = Counter(role for roles in param_roles.values() for role in roles)
        all_three = sum({"lower", "same", "higher"}.issubset(roles) for roles in param_roles.values())
        m11c_coverage = {
            "profile_skus": len(m11c),
            "secondary_nonempty": sum(bool(row.get("secondary_battlefield_codes_json")) for row in m11c.values()),
            "opportunity_nonempty": sum(bool(row.get("opportunity_battlefield_codes_json")) for row in m11c.values()),
            "average_opportunity_count": round(
                sum(len(row.get("opportunity_battlefield_codes_json") or []) for row in m11c.values()) / max(len(m11c), 1),
                4,
            ),
            "observable_reachable_excluded_skus": sum(bool(_observable_reachable_excluded(row)) for row in m11c.values()),
            "average_entered_battlefield_count": round(
                sum(len(_entered_battlefields(row)) for row in m11c.values()) / max(len(m11c), 1),
                4,
            ),
            "battlefield_universe_count": len(ALL_TV_BATTLEFIELDS),
        }

        synthetic_candidates.sort(reverse=True)
        claim_examples = sorted(
            claim_realization_contrast,
            key=lambda sku: (
                len(claim_realization_contrast[sku]["peer_contradicted_claim_codes"]),
                len(claim_realization_contrast[sku]["peer_not_realized_claim_codes"]),
                sku,
            ),
            reverse=True,
        )[:8]

        no_observable_expansion = [
            sku for sku in sorted(m11c) if not _observable_reachable_excluded(m11c[sku])
        ][:3]
        cohort_skus = {
            "C01_65E7Q_MULTI_LAYER": ["TV00029112", "TV00027541", "TV00029020", "TV00027899"],
            "C02_DIRECT_TIER": ["TV00027524", "TV00027913"],
            "C03_SYNTHETIC_DONOR_RICH": [sku for _, sku in synthetic_candidates[:3]],
            "C04_SAME_CLAIM_DIFFERENT_REALIZATION": claim_examples[:3],
            "C05_NO_STRONG_OWN_PRICE_CURVE": [
                sku
                for sku, row in markets.items()
                if not (
                    int(row.get("active_week_count") or 0) >= 8
                    and int(row.get("platform_count") or 0) >= 2
                    and float(row.get("price_volatility") or 0) > 0
                )
            ][:3],
            "C06_EXISTING_AND_EXCLUDED_BATTLEFIELD": ["TV00029112"],
            "C07_NO_OBSERVABLE_EXPANSION": no_observable_expansion,
            "C08_NEGATIVE_MIXED_USER_VALUE": ["TV00028087"],
        }

        contribution_by_sku: dict[str, list[dict[str, Any]]] = {}
        for row in m11d_rows:
            contribution_by_sku.setdefault(row["sku_code"], []).append(row)

        lineage_material: dict[str, Any] = {}
        for cohort_id, skus in cohort_skus.items():
            lineage_material[cohort_id] = {}
            for sku in skus:
                lineage_material[cohort_id][sku] = {
                    "market": (markets.get(sku) or {}).get("result_hash"),
                    "m11c": (m11c.get(sku) or {}).get("profile_hash"),
                    "param": (params.get(sku) or {}).get("profile_hash"),
                    "claim": (claims.get(sku) or {}).get("profile_hash"),
                    "comment": (comments.get(sku) or {}).get("profile_hash"),
                    "m12d": (m12d.get(sku) or {}).get("result_hash"),
                    "m11d": sorted(row.get("result_hash") for row in contribution_by_sku.get(sku, []) if row.get("result_hash")),
                }

        target_sku = "TV00029112"
        target = markets[target_sku]
        target_profile = m11c[target_sku]
        target_fixture = {
            "identity": {
                "sku_code": target_sku,
                "brand_name": target.get("brand_name"),
                "model_name": target.get("model_name"),
                "screen_size_inch": target.get("screen_size_inch"),
            },
            "market": {
                key: target.get(key)
                for key in (
                    "price_wavg",
                    "sales_volume_total",
                    "sales_amount_total",
                    "active_week_count",
                    "platform_count",
                    "price_min",
                    "price_max",
                    "price_volatility",
                    "same_pool_price_percentile",
                    "same_pool_volume_percentile",
                    "same_pool_amount_percentile",
                )
            },
            "battlefields": {
                "primary": target_profile.get("primary_battlefield_code"),
                "secondary": target_profile.get("secondary_battlefield_codes_json") or [],
                "opportunity": target_profile.get("opportunity_battlefield_codes_json") or [],
                "entered": sorted(entered[target_sku]),
                "excluded": sorted(ALL_TV_BATTLEFIELDS - entered[target_sku]),
                "observable_reachable_excluded": sorted(_observable_reachable_excluded(target_profile)),
                "summary": target_profile.get("battlefield_summary_json"),
            },
            "peer_counts": peer_counts[target_sku],
            "param_tier_roles": sorted(param_roles.get(target_sku, set())),
            "same_claim_realization_contrast": claim_realization_contrast.get(target_sku),
            "m11d_current_allocation": contribution_by_sku.get(target_sku, []),
            "strict_amount_allowed": False,
            "strict_amount_blockers": [
                "published_lineage_conflict",
                "bundle_collinearity",
                "observational_counterfactual_not_yet_balanced",
            ],
        }

        source_versions = {
            "M03B": "m03b_tv_param_profile_v0.2",
            "M04C": "m04c_tv_claim_fact_profile_v0.2",
            "M05C": "m05c_tv_comment_fact_profile_v0.2",
            "M07": "m07_market_profile_v2/full_observed_window",
            "M11C": "m11c_tv_value_battlefield_profile_v0.4",
            "M11D": "m11d_semantic_market_allocation_v0.1",
            "M12D": "m12d_sku_purchase_reason_profile_v0.1",
            "M14": "core3_mvp_real_data_v2_m14_v1/review_required",
        }
        output = {
            "schema_version": "sellpoint_value_pm_v5_g01_probe_v1",
            "project_id": PROJECT_ID,
            "category_code": CATEGORY_CODE,
            "read_only": True,
            "source_versions": source_versions,
            "universe": {
                "market_target_skus": len(markets),
                "m03b_skus": len(params),
                "m04c_skus": len(claims),
                "m05c_skus": len(comments),
                "m11c_skus": len(m11c),
                "m11d_skus": len(contribution_by_sku),
                "m12d_skus": len(m12d),
            },
            "counterfactual_coverage": dict(sorted(coverage.items())),
            "parameter_tier_roles": {
                "comparable_skus": len(param_roles),
                "lower": role_counts["lower"],
                "same": role_counts["same"],
                "higher": role_counts["higher"],
                "all_three": all_three,
            },
            "battlefield_coverage": m11c_coverage,
            "m14": m14_summary,
            "high_low_archetype_field_gate": {
                "strong_own_market_series_skus": coverage["own_price_curve_strong"],
                "market_plus_m11c_skus": sum(sku in m11c for sku in markets),
                "market_plus_m11c_plus_m11d_skus": sum(sku in m11c and sku in contribution_by_sku for sku in markets),
                "promotion_flag": "available_as_suspect_only",
                "inventory": "unavailable",
                "causal_claim_allowed": False,
            },
            "cohort_skus": cohort_skus,
            "cohort_lineage": lineage_material,
            "cohort_input_sha256": {
                cohort_id: _canonical_hash(rows) for cohort_id, rows in lineage_material.items()
            },
            "cohort_manifest_sha256": _canonical_hash(lineage_material),
            "target_65e7q": target_fixture,
        }
        output["probe_result_sha256"] = _canonical_hash(output)
        print(json.dumps(_jsonable(output), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        db.rollback()


if __name__ == "__main__":
    main()
