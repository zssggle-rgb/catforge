#!/usr/bin/env python3
"""Validate competitor consumption against the frozen G06 M12D fixture."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.core3_real_data.analyst.anchor_substitutability import (  # noqa: E402
    ValueAnchorMatcher,
)
from app.services.core3_real_data.analyst.competitor_answer import (  # noqa: E402
    build_competitor_answer,
)
from app.services.core3_real_data.analyst.competitor_pm_report import (  # noqa: E402
    pm_business_output_issue,
)
from app.services.core3_real_data.analyst.purchase_pressure_comparison import (  # noqa: E402
    PurchasePressureComparator,
)
from app.services.core3_real_data.analyst.replacement_pressure import (  # noqa: E402
    ReplacementPressureClassifier,
    ReplacementPressureInput,
)
from app.services.core3_real_data.analyst.sop_orchestrators import (  # noqa: E402
    _m12d_business_profile_summary,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (  # noqa: E402
    M12DDownstreamReadContract,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
G06_FIXTURE_VERSION = "m12d_rp_g06_validated_v0.1"
ESTABLISHED = {"established", "established_limited"}


def main() -> int:
    args = parse_args()
    fixture = json.loads(Path(args.g06_fixture).read_text(encoding="utf-8"))
    if fixture.get("fixture_version") != G06_FIXTURE_VERSION:
        raise ValueError("G07 requires the frozen G06 validated fixture")

    category_results: dict[str, Any] = {}
    all_top3_rows: list[dict[str, Any]] = []
    failed_checks: list[str] = []
    contracts_by_category: dict[str, dict[str, M12DDownstreamReadContract]] = {}

    for category in ("TV", "AC"):
        profiles = fixture["categories"][category]["focus_profiles"]
        contracts = {
            str(profile["sku_code"]): contract_from_g06_profile(
                category=category,
                taxonomy_version=fixture["categories"][category]["taxonomy_version"],
                profile=profile,
            )
            for profile in profiles
        }
        contracts_by_category[category] = contracts
        result = validate_category(category, profiles, contracts)
        category_results[category] = result
        all_top3_rows.extend(result["top3_rows"])
        failed_checks.extend(
            f"{category.lower()}_{name}"
            for name, passed in result["checks"].items()
            if not passed
        )

    replay = replay_65e7q(
        source_path=Path(args.tv_65e7q_candidate_set),
        contracts=contracts_by_category["TV"],
    )
    failed_checks.extend(
        f"tv_65e7q_{name}" for name, passed in replay["checks"].items() if not passed
    )
    all_top3_rows.extend(replay["top3_rows"])

    payload = {
        "task_id": "M12D-RP-G07",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fixture": str(args.g06_fixture),
        "source_fixture_version": fixture["fixture_version"],
        "scope": {
            "m12d_policy": "只消费 G06 fixture，不生成、不修正 M12D。",
            "tv_target_count": len(category_results["TV"]["targets"]),
            "ac_target_count": len(category_results["AC"]["targets"]),
            "tv_65e7q_real_candidate_replay": True,
        },
        "categories": category_results,
        "tv_65e7q_replay": replay,
        "acceptance": {"passed": not failed_checks, "failed_checks": failed_checks},
    }
    write_outputs(args, payload, all_top3_rows)
    print(
        json.dumps(
            {
                "status": "ok" if not failed_checks else "failed",
                "tv_targets": len(category_results["TV"]["targets"]),
                "ac_targets": len(category_results["AC"]["targets"]),
                "tv_65e7q_old_top3": replay["old_top3"],
                "tv_65e7q_new_top3": replay["new_top3"],
                "failed_checks": failed_checks,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failed_checks else 1


def validate_category(
    category: str,
    profiles: list[dict[str, Any]],
    contracts: dict[str, M12DDownstreamReadContract],
) -> dict[str, Any]:
    target_results: list[dict[str, Any]] = []
    top3_rows: list[dict[str, Any]] = []
    proposition_pair_count = 0
    proposition_profile_count = sum(
        bool(profile.get("proposition_anchors")) for profile in profiles
    )
    proposition_scoring_failures = 0
    proposition_language_failures = 0
    pressure_separation_failures = 0
    ranking_trace_failures = 0
    internal_language_failures = 0

    for target_index, target_profile in enumerate(profiles):
        target_sku = str(target_profile["sku_code"])
        target_contract = contracts[target_sku]
        target = synthetic_product(category, target_profile, index=target_index)
        competitor_items: list[dict[str, Any]] = []
        pair_audits: list[dict[str, Any]] = []
        for candidate_index, candidate_profile in enumerate(profiles):
            candidate_sku = str(candidate_profile["sku_code"])
            if candidate_sku == target_sku:
                continue
            candidate_contract = contracts[candidate_sku]
            base_item = synthetic_candidate_item(
                category,
                candidate_profile,
                index=candidate_index,
            )
            item, audit = consume_pair(
                target=target,
                base_item=base_item,
                target_contract=target_contract,
                candidate_contract=candidate_contract,
            )
            competitor_items.append(item)
            pair_audits.append(audit)
            if audit["proposition_only_anchors"]:
                proposition_pair_count += 1
                if audit["proposition_counted_as_shared"]:
                    proposition_scoring_failures += 1

        answer = build_competitor_answer(
            target=target,
            target_fact_brief={"sections": {}},
            competitors=competitor_items,
            top_n=3,
            with_report="markdown",
        )
        top_competitors = answer["top_competitors"]
        detailed_markdown = str(answer["report_payload"].get("markdown") or "")
        pm_markdown = str(answer["pm_comparison_report_payload"].get("markdown") or "")
        pm_issue = pm_business_output_issue(pm_markdown)
        if pm_issue:
            internal_language_failures += 1
        top_has_proposition = bool(target_profile.get("proposition_anchors")) or any(
            bool(
                (item.get("candidate_purchase_reason_profile") or {}).get(
                    "proposition_reasons_cn"
                )
            )
            for item in top_competitors
        )
        if (
            top_has_proposition
            and "产品希望传达但尚未观察到用户承接" not in pm_markdown
        ):
            proposition_language_failures += 1
        if (
            "购买阻力比较" not in detailed_markdown
            or "替代压力比较" not in detailed_markdown
        ):
            pressure_separation_failures += 1
        if "的威胁来自" in detailed_markdown:
            pressure_separation_failures += 1

        target_top3: list[str] = []
        for rank, item in enumerate(top_competitors, start=1):
            candidate = item.get("candidate") or {}
            candidate_sku = str(candidate.get("sku_code") or "")
            target_top3.append(candidate_sku)
            trace = item.get("ranking_trace") or {}
            trace_ok = bool(trace.get("selection_effect_cn")) and not bool(
                trace.get("version_wide_degradation_applied")
            )
            if not trace_ok:
                ranking_trace_failures += 1
            top3_rows.append(
                {
                    "category": category,
                    "target_sku_code": target_sku,
                    "target_name": target_profile["display_name_cn"],
                    "rank": rank,
                    "candidate_sku_code": candidate_sku,
                    "candidate_name": display_name(candidate),
                    "comparison_mode": trace.get("candidate_comparison_mode"),
                    "purchase_reason_overlap_points": trace.get(
                        "purchase_reason_overlap_points"
                    ),
                    "replacement_pressure_points": trace.get(
                        "replacement_pressure_points"
                    ),
                    "selection_effect_cn": trace.get("selection_effect_cn"),
                    "baseline_rank": None,
                    "migration_cn": "G06 fixture 消费回归，无旧 Top 3 基准。",
                }
            )

        target_results.append(
            {
                "target_sku_code": target_sku,
                "target_name": target_profile["display_name_cn"],
                "target_comparison_mode": target_contract.capabilities.comparison_mode,
                "top3": target_top3,
                "pair_count": len(pair_audits),
                "proposition_pair_count": sum(
                    bool(row["proposition_only_anchors"]) for row in pair_audits
                ),
                "facts_only_candidate_count": sum(
                    row["candidate_comparison_mode"] == "facts_only"
                    for row in pair_audits
                ),
                "report_checks": {
                    "replacement_pressure_separate": "替代压力比较"
                    in detailed_markdown,
                    "purchase_pressure_separate": "购买阻力比较" in detailed_markdown,
                    "no_threat_contradiction": "的威胁来自" not in detailed_markdown,
                    "pm_business_language": pm_issue is None,
                },
            }
        )

    checks = {
        "target_coverage": len(target_results) >= (10 if category == "TV" else 10),
        "tv_65e7q_covered": category != "TV"
        or any(row["target_sku_code"] == "TV00029112" for row in target_results),
        "proposition_sample_covered": proposition_profile_count > 0,
        "proposition_never_scores_as_shared_reason": proposition_scoring_failures == 0,
        "proposition_business_language": proposition_language_failures == 0,
        "replacement_and_purchase_pressure_separate": pressure_separation_failures == 0,
        "top3_trace_complete": ranking_trace_failures == 0,
        "pm_business_language_clean": internal_language_failures == 0,
    }
    return {
        "category": category,
        "summary": {
            "target_count": len(target_results),
            "pair_count": sum(row["pair_count"] for row in target_results),
            "proposition_pair_count": proposition_pair_count,
            "proposition_profile_count": proposition_profile_count,
            "proposition_scoring_failure_count": proposition_scoring_failures,
            "proposition_language_failure_count": proposition_language_failures,
            "pressure_separation_failure_count": pressure_separation_failures,
            "ranking_trace_failure_count": ranking_trace_failures,
            "pm_business_language_failure_count": internal_language_failures,
        },
        "targets": target_results,
        "top3_rows": top3_rows,
        "checks": checks,
    }


def replay_65e7q(
    *, source_path: Path, contracts: dict[str, M12DDownstreamReadContract]
) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    target = source["target"]
    target_contract = contracts["TV00029112"]
    source_set = source["result"]["competitor_set"]
    old_top3 = [
        str(item["candidate"]["sku_code"])
        for item in source["result"]["competitor_answer"]["top_competitors"]
    ]
    competitors: list[dict[str, Any]] = []
    for source_item in source_set["candidates"]:
        candidate_sku = str(source_item["candidate"]["sku_code"])
        candidate_contract = contracts.get(candidate_sku) or not_found_contract(
            category="TV", sku_code=candidate_sku
        )
        item, _audit = consume_pair(
            target=target,
            base_item=source_item,
            target_contract=target_contract,
            candidate_contract=candidate_contract,
        )
        competitors.append(item)
    answer = build_competitor_answer(
        target=target,
        target_fact_brief=source_set["target_fact_brief"],
        target_claim_value=source_set.get("target_claim_value"),
        target_claim_contribution=source_set.get("target_claim_contribution"),
        competitors=competitors,
        top_n=3,
        with_report="markdown",
    )
    new_top = answer["top_competitors"]
    new_top3 = [str(item["candidate"]["sku_code"]) for item in new_top]
    top3_rows = []
    for rank, item in enumerate(new_top, start=1):
        candidate = item["candidate"]
        sku_code = str(candidate["sku_code"])
        old_rank = old_top3.index(sku_code) + 1 if sku_code in old_top3 else None
        trace = item.get("ranking_trace") or {}
        top3_rows.append(
            {
                "category": "TV",
                "target_sku_code": "TV00029112",
                "target_name": "海信 65E7Q",
                "rank": rank,
                "candidate_sku_code": sku_code,
                "candidate_name": display_name(candidate),
                "comparison_mode": trace.get("candidate_comparison_mode"),
                "purchase_reason_overlap_points": trace.get(
                    "purchase_reason_overlap_points"
                ),
                "replacement_pressure_points": trace.get("replacement_pressure_points"),
                "selection_effect_cn": trace.get("selection_effect_cn"),
                "baseline_rank": old_rank,
                "migration_cn": (
                    f"旧第{old_rank}名保持/迁移。"
                    if old_rank
                    else "由 G06 已验证的 SKU 能力和其他业务维度共同进入 Top 3。"
                ),
            }
        )
    fixture_uncovered_candidates = [
        str(item["candidate"]["sku_code"])
        for item in answer["all_candidates"]
        if (item.get("candidate_purchase_reason_profile") or {}).get("comparison_mode")
        == "blocked"
    ]
    new_top_modes = [
        str((item.get("ranking_trace") or {}).get("candidate_comparison_mode"))
        for item in new_top
    ]
    detailed_markdown = str(answer["report_payload"].get("markdown") or "")
    pm_markdown = str(answer["pm_comparison_report_payload"].get("markdown") or "")
    return {
        "source_path": str(source_path),
        "old_top3": old_top3,
        "new_top3": new_top3,
        "fixture_uncovered_candidates": fixture_uncovered_candidates,
        "top3_candidate_modes": new_top_modes,
        "top3_rows": top3_rows,
        "checks": {
            "three_candidates_selected": len(new_top3) == 3,
            "fixture_uncovered_not_in_top3": not set(new_top3)
            & set(fixture_uncovered_candidates),
            "ranking_trace_complete": all(
                row["selection_effect_cn"] for row in top3_rows
            ),
            "no_version_wide_degradation": all(
                not (item.get("ranking_trace") or {}).get(
                    "version_wide_degradation_applied"
                )
                for item in new_top
            ),
            "replacement_and_purchase_pressure_separate": "替代压力比较"
            in detailed_markdown
            and "购买阻力比较" in detailed_markdown,
            "no_threat_contradiction": "的威胁来自" not in detailed_markdown,
            "pm_business_language_clean": pm_business_output_issue(pm_markdown) is None,
        },
    }


def consume_pair(
    *,
    target: dict[str, Any],
    base_item: dict[str, Any],
    target_contract: M12DDownstreamReadContract,
    candidate_contract: M12DDownstreamReadContract,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matcher = ValueAnchorMatcher()
    anchor_result = matcher.match(
        target_contract=target_contract,
        candidate_contract=candidate_contract,
    )
    semantic_scores = semantic_score_map(base_item.get("semantic_overlap") or {})
    pressure_result = ReplacementPressureClassifier().classify(
        ReplacementPressureInput(
            purchase_pool_level="P0",
            purchase_pool_score=Decimal("1.00"),
            anchor_substitutability=anchor_result,
            price_gap_pct_to_target=(base_item.get("candidate") or {}).get(
                "price_gap_pct_to_target"
            ),
            weighted_overlap=semantic_scores,
            market_validation_level="strong",
            candidate_config_advantage_score=(
                Decimal("0.75") if anchor_result.candidate_stronger_anchors else None
            ),
        )
    )
    purchase_pressure = PurchasePressureComparator().compare(
        target_contract=target_contract,
        candidate_contract=candidate_contract,
    )
    value_anchor = anchor_result.to_legacy_value_anchor()
    item = {
        **base_item,
        "target_purchase_reason_profile": _m12d_business_profile_summary(
            target_contract
        ),
        "candidate_purchase_reason_profile": _m12d_business_profile_summary(
            candidate_contract
        ),
        "anchor_substitutability": value_anchor,
        "value_anchor": value_anchor,
        "replacement_pressure": pressure_result.to_legacy_replacement_pressure(),
        "purchase_pressure_comparison": purchase_pressure.to_business_payload(),
    }
    shared = set(anchor_result.shared_core_anchors)
    propositions = set(anchor_result.proposition_only_anchors)
    return item, {
        "candidate_sku_code": str((base_item.get("candidate") or {}).get("sku_code")),
        "candidate_comparison_mode": candidate_contract.capabilities.comparison_mode,
        "proposition_only_anchors": sorted(propositions),
        "proposition_counted_as_shared": bool(shared & propositions),
        "anchor_substitutability_score": anchor_result.anchor_substitutability_score,
        "replacement_pressure_score": pressure_result.replacement_pressure_score,
        "purchase_pressure_comparison_allowed": purchase_pressure.comparison_allowed,
    }


def contract_from_g06_profile(
    *, category: str, taxonomy_version: str, profile: dict[str, Any]
) -> M12DDownstreamReadContract:
    sku_code = str(profile["sku_code"])
    status = str(profile["new_status"])
    anchors = [contract_anchor(row, profile) for row in profile["anchors"]]
    anchor_index = {str(row["anchor_code"]): row for row in anchors}
    core_codes = [str(value) for value in profile.get("new_core") or []]
    established_codes = [
        str(row["anchor_code"])
        for row in anchors
        if str(row["establishment_status"]) in ESTABLISHED
    ]
    proposition_codes = [
        str(row["anchor_code"])
        for row in anchors
        if str(row["establishment_status"]) == "proposition_only"
    ]
    supporting_codes = [
        str(row["anchor_code"])
        for row in anchors
        if str(row["role"]) == "supporting"
        and str(row["establishment_status"]) in ESTABLISHED
    ]
    weak_codes = [
        str(row["anchor_code"])
        for row in anchors
        if str(row["role"]) == "weak_expression"
    ]
    risk_codes = [
        str(row["anchor_code"]) for row in anchors if str(row["role"]) == "risk_drag"
    ]
    comparison_mode = (
        "strong"
        if core_codes
        else "limited"
        if established_codes or proposition_codes
        else "facts_only"
    )
    return M12DDownstreamReadContract.model_validate(
        {
            "found": True,
            "lookup_key": {
                "project_id": PROJECT_ID,
                "category_code": category,
                "batch_id": f"g06-fixture:{category}",
                "m12d_profile_version": taxonomy_version,
                "sku_code": sku_code,
            },
            "consumption_state": "published_ready"
            if comparison_mode == "strong"
            else "published_degraded",
            "downstream_action": "normal_pair_scoring"
            if comparison_mode == "strong"
            else "degraded_pair_scoring",
            "release_quality_status": "ready",
            "capabilities": {
                "comparison_mode": comparison_mode,
                "fact_dimensions_allowed": True,
                "proposition_comparison_allowed": bool(proposition_codes),
                "established_reason_comparison_allowed": bool(established_codes),
                "strong_reason_comparison_allowed": bool(core_codes),
                "pressure_comparison_allowed": bool(established_codes),
            },
            "profile": {
                "project_id": PROJECT_ID,
                "category_code": category,
                "batch_id": f"g06-fixture:{category}",
                "product_category": category,
                "m12d_profile_version": taxonomy_version,
                "sku_code": sku_code,
                "display_name_cn": profile["display_name_cn"],
                "status": status,
                "profile_confidence": profile["profile_confidence"],
                "core_reasons_cn": [
                    str(anchor_index[code]["anchor_cn"])
                    for code in core_codes
                    if code in anchor_index
                ],
                "core_payment_anchors": core_codes,
                "supporting_anchors": supporting_codes,
                "weak_expression_anchors": weak_codes,
                "risk_drag_anchors": risk_codes,
                "established_anchors": established_codes,
                "proposition_anchors": proposition_codes,
                "pressure_summary": profile.get("pressure_summary") or {},
                "anchors": anchors,
                "review_required": bool(profile.get("review_required")),
            },
        }
    )


def contract_anchor(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    establishment_status = str(row["establishment_status"])
    score = Decimal(str(row.get("establishment_score") or 0))
    validation = str(row.get("user_validation_status") or "not_observed")
    domains = ["param_fact", "fact_claim"]
    if establishment_status in ESTABLISHED:
        domains.append("semantic_scene")
    if validation in {"user_supported", "user_validated"}:
        domains.append("comment_perception")
    if validation in {"market_supported", "user_validated"}:
        domains.append("market_acceptance")
    strength = (
        "strong"
        if score >= 9
        else "medium"
        if score >= 7
        else "weak"
        if score > 0
        else "insufficient"
    )
    return {
        "anchor_code": row["anchor_code"],
        "anchor_cn": row["anchor_cn"],
        "anchor_rank": 1,
        "role": row["role"],
        "evidence_strength": strength,
        "confidence": profile["profile_confidence"],
        "establishment_status": establishment_status,
        "establishment_score": str(score),
        "establishment_domains": domains,
        "user_validation_status": validation,
        "core_eligible": row.get("core_eligible"),
        "pressure_level": row.get("pressure_level") or "unassessed",
        "pressure_summary_cn": row.get("pressure_summary_cn") or "",
        "evidence_domains": domains,
        "support_summary_cn": row.get("support_summary_cn") or "",
    }


def not_found_contract(*, category: str, sku_code: str) -> M12DDownstreamReadContract:
    return M12DDownstreamReadContract.model_validate(
        {
            "found": False,
            "lookup_key": {
                "project_id": PROJECT_ID,
                "category_code": category,
                "batch_id": f"g06-fixture:{category}",
                "m12d_profile_version": "g06-not-found",
                "sku_code": sku_code,
            },
            "consumption_state": "not_found",
            "downstream_action": "block_target_or_drop_candidate",
        }
    )


def synthetic_product(
    category: str, profile: dict[str, Any], *, index: int
) -> dict[str, Any]:
    if category == "TV":
        return {
            "sku_code": profile["sku_code"],
            "brand_name": "验证样本",
            "model_name": profile["display_name_cn"],
            "product_category": "TV",
            "screen_size_inch": 65,
            "size_tier": "large_60_69",
            "price_band_in_size_tier": "mid_high",
            "weighted_price": 5000 + index * 20,
            "avg_weekly_sales_volume": 100,
        }
    return {
        "sku_code": profile["sku_code"],
        "brand_name": "验证样本",
        "model_name": profile["display_name_cn"],
        "product_category": "AC",
        "size_tier": "floor_hp_3",
        "price_band_in_size_tier": "mid_high",
        "weighted_price": 6000 + index * 20,
        "avg_weekly_sales_volume": 100,
    }


def synthetic_candidate_item(
    category: str, profile: dict[str, Any], *, index: int
) -> dict[str, Any]:
    candidate = synthetic_product(category, profile, index=index)
    candidate["price_gap_pct_to_target"] = Decimal((index % 5) - 2) / Decimal("100")
    score = Decimal("0.78") - Decimal(index % 4) * Decimal("0.04")
    if category == "TV":
        battlefield = "BF_PREMIUM_PICTURE_UPGRADE"
        task = "TASK_PREMIUM_PICTURE_EXPERIENCE"
        group = "TG_PREMIUM_AV_ENTHUSIAST"
    else:
        battlefield = "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH"
        task = "TASK_FAST_COOL_HEAT"
        group = "TG_LIVING_ROOM_LARGE_SPACE"
    return {
        "candidate": candidate,
        "semantic_overlap": {
            "value_battlefield": {
                "weighted_overlap_score": score,
                "matched_codes": [battlefield],
            },
            "user_task": {
                "weighted_overlap_score": score,
                "matched_codes": [task],
            },
            "target_group": {
                "weighted_overlap_score": score,
                "matched_codes": [group],
            },
        },
        "param_claim_overlap": {},
        "sales_overlap": {
            "overlap_week_count": 8,
            "candidate": {"avg_weekly_sales_volume_on_overlap_weeks": 80},
        },
        "candidate_fact_brief": {"sections": {}},
    }


def semantic_score_map(payload: dict[str, Any]) -> dict[str, Decimal]:
    return {
        key: Decimal(
            str((payload.get(source_key) or {}).get("weighted_overlap_score") or 0)
        )
        for key, source_key in (
            ("battlefield", "value_battlefield"),
            ("user_task", "user_task"),
            ("target_group", "target_group"),
        )
    }


def display_name(product: dict[str, Any]) -> str:
    return " ".join(
        str(value).strip()
        for value in (product.get("brand_name"), product.get("model_name"))
        if str(value or "").strip()
    ) or str(product.get("sku_code") or "产品")


def write_outputs(
    args: argparse.Namespace,
    payload: dict[str, Any],
    top3_rows: list[dict[str, Any]],
) -> None:
    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    output_markdown = Path(args.output_markdown)
    output_fixture = Path(args.output_fixture)
    for path in (output_json, output_csv, output_markdown, output_fixture):
        path.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    with output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = (
            "category",
            "target_sku_code",
            "target_name",
            "rank",
            "candidate_sku_code",
            "candidate_name",
            "comparison_mode",
            "purchase_reason_overlap_points",
            "replacement_pressure_points",
            "selection_effect_cn",
            "baseline_rank",
            "migration_cn",
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(top3_rows)
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    regression_fixture = {
        "fixture_version": "m12d_rp_g07_competitor_consumption_v0.1",
        "task_id": payload["task_id"],
        "generated_at": payload["generated_at"],
        "source_fixture_version": payload["source_fixture_version"],
        "categories": {
            category: {
                "summary": result["summary"],
                "checks": result["checks"],
                "targets": result["targets"],
            }
            for category, result in payload["categories"].items()
        },
        "tv_65e7q_replay": payload["tv_65e7q_replay"],
    }
    output_fixture.write_text(
        json.dumps(regression_fixture, ensure_ascii=False, indent=2, default=str)
        + "\n",
        encoding="utf-8",
    )


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M12D-RP-G07 竞品智能体消费与 Top 3 回归",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- M12D 来源：只消费 G06 validated fixture；未生成、未修正、未发布 M12D。",
        "",
    ]
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        summary = result["summary"]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- 目标 SKU：`{summary['target_count']}`；竞品 pair：`{summary['pair_count']}`。",
                f"- proposition 画像：`{summary['proposition_profile_count']}`；命中目标核心 pair：`{summary['proposition_pair_count']}`；误计购买理由重合：`{summary['proposition_scoring_failure_count']}`；业务语言失败：`{summary['proposition_language_failure_count']}`。",
                f"- 替代压力/购买阻力未分开：`{summary['pressure_separation_failure_count']}`；Top 3 追溯失败：`{summary['ranking_trace_failure_count']}`。",
                f"- PM 业务语言失败：`{summary['pm_business_language_failure_count']}`。",
                f"- 检查项：`{json.dumps(result['checks'], ensure_ascii=False)}`。",
                "",
            ]
        )
    replay = payload["tv_65e7q_replay"]
    lines.extend(
        [
            "## 海信 65E7Q 真实候选池回放",
            "",
            f"- 旧 Top 3：`{replay['old_top3']}`。",
            f"- G06 消费后 Top 3：`{replay['new_top3']}`。",
            f"- G06 validated fixture 未覆盖、因此本轮不能使用购买理由维度进入 Top 3 的候选：`{replay['fixture_uncovered_candidates']}`。该状态只代表 G07 fixture 范围，不代表正式全量发布后缺少画像。",
            f"- 检查项：`{json.dumps(replay['checks'], ensure_ascii=False)}`。",
            "",
            "## 总体验收",
            "",
            f"- G07：`{'通过' if payload['acceptance']['passed'] else '未通过'}`。",
            f"- 未通过项：`{payload['acceptance']['failed_checks']}`。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--g06-fixture",
        default=str(
            REPO_ROOT
            / "docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G06_validated_fixture.json"
        ),
    )
    parser.add_argument(
        "--tv-65e7q-candidate-set",
        default=str(REPO_ROOT / "tmp/ca_g08/65e7q_competitor_answer_205.json"),
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-fixture", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
