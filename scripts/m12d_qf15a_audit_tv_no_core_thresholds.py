#!/usr/bin/env python3
"""Audit TV no-core profiles and simulate bounded threshold relaxations read-only."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.core3_real_data.constants import CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION
from app.services.core3_real_data.purchase_reason_anchor_candidate_generator import (
    AnchorCandidateGenerator,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import M12DAnchorTaxonomyLoader
from app.services.core3_real_data.purchase_reason_context_builder import SkuPurchaseReasonContextBuilder
from app.services.core3_real_data.purchase_reason_profile_scoring import (
    EvidenceStrengthScorer,
    ProfileConfidenceScorer,
    ReasonRoleClassifier,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY = "TV"
EXPECTED_SKU_COUNT = 377
EXPECTED_BASELINE_STATUS = {"ready": 238, "ready_limited": 94, "weak_expression_only": 45}
EXPECTED_NO_CORE_COUNT = 139
PROFILE_READY_CONFIDENCE = Decimal("0.7000")
CORE_ANCHOR_LIMIT = 3
CORE_RANK_WEIGHTS = (Decimal("0.6000"), Decimal("0.2500"), Decimal("0.1500"))
STRONG_DOMAINS = {"param_fact", "comment_perception", "claim_value", "market_acceptance"}
HARD_RISK_FLAGS = {"comment_negative_dominates", "claim_value_drag_factor"}
OBJECTIVE_PRICE_REASON_CODES = {
    "low_price_core_experience_intact",
    "same_price_core_config_gain",
}
SUBJECTIVE_PRICE_REASON_CODES = {
    "picture_upgrade_justifies_price",
    "same_size_picture_step_up",
    "worth_paying_more_for_experience_upgrade",
    "av_user_willing_to_pay_for_picture",
}
PRICE_REASON_CODES = OBJECTIVE_PRICE_REASON_CODES | SUBJECTIVE_PRICE_REASON_CODES
UNSAFE_EVIDENCE_FLAGS = {
    "comment_claim_contradiction",
    "m12c_related_claim_negative",
    "market_pool_insufficient",
    "price_band_sample_insufficient",
    "size_pool_insufficient",
}
FOCUS_SKUS = {
    "TV00029112": "海信 65E7Q",
    "TV00029936": "创维 65A7H PRO",
    "TV00027801": "TCL 65Q9L PRO",
    "TV00028829": "创维 65A6F ULTRA",
    "TV00029020": "小米 L65MC-SP",
}
DOWNSTREAM_TABLES = (
    "core3_sku_purchase_reason_profile",
    "core3_sku_purchase_reason_anchor",
    "core3_purchase_reason_profile_version",
)


@dataclass(frozen=True)
class Scenario:
    code: str
    name_cn: str
    strong_score_threshold: Decimal
    relax_objective_price_gate: bool = False
    relax_all_price_gate: bool = False
    only_baseline_no_core: bool = False
    block_unsafe_evidence: bool = False
    require_anchor_aligned_comment: bool = False
    intended_safety: str = "review"


SCENARIOS = (
    Scenario(
        code="baseline",
        name_cn="现行门槛",
        strong_score_threshold=Decimal("9.0000"),
        intended_safety="baseline",
    ),
    Scenario(
        code="score_8_5_only",
        name_cn="强证据分数 9.0 降至 8.5，其余门槛不变",
        strong_score_threshold=Decimal("8.5000"),
    ),
    Scenario(
        code="score_8_0_only",
        name_cn="强证据分数 9.0 降至 8.0，其余门槛不变",
        strong_score_threshold=Decimal("8.0000"),
    ),
    Scenario(
        code="guarded_score_8_no_core_only",
        name_cn="仅无核心 SKU 启用 8.0 分兜底，并排除冲突、负向和样本风险",
        strong_score_threshold=Decimal("8.0000"),
        only_baseline_no_core=True,
        block_unsafe_evidence=True,
        require_anchor_aligned_comment=True,
        intended_safety="bounded",
    ),
    Scenario(
        code="objective_price_gate_only",
        name_cn="仅客观性价比理由使用参数+市场+场景替代价格价值门槛",
        strong_score_threshold=Decimal("9.0000"),
        relax_objective_price_gate=True,
        intended_safety="bounded",
    ),
    Scenario(
        code="objective_price_plus_score_8_5",
        name_cn="客观性价比门槛分型，并将强证据分数降至 8.5",
        strong_score_threshold=Decimal("8.5000"),
        relax_objective_price_gate=True,
    ),
    Scenario(
        code="unsafe_all_price_plus_score_8_0",
        name_cn="所有价格理由取消价格价值门槛，并将强证据分数降至 8.0",
        strong_score_threshold=Decimal("8.0000"),
        relax_all_price_gate=True,
        intended_safety="unsafe_probe",
    ),
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_csv = Path(args.output_csv)
    for path in (output_json, output_markdown, output_csv):
        path.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        guard_before = capture_guard(db)
        audit = audit_tv(db)
        guard_after = capture_guard(db)
    if guard_before != guard_after:
        raise RuntimeError("TV no-core threshold audit changed persisted M12D tables")

    audit["task_id"] = "M12D-QF-15A"
    audit["generated_at"] = datetime.now(timezone.utc).isoformat()
    audit["downstream_guard"] = {
        "before": guard_before,
        "after": guard_after,
        "unchanged": True,
    }
    assert_baseline(audit)
    output_json.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(audit), encoding="utf-8")
    write_csv(output_csv, audit["no_core_sku_audit"])
    print(
        json.dumps(
            {
                "status": "ok",
                "sku_count": audit["baseline"]["sku_count"],
                "no_core_count": audit["baseline"]["no_core_count"],
                "scenario_summary": {
                    item["scenario_code"]: {
                        "no_core_promoted": item["no_core_promoted_count"],
                        "ready_rate": item["ready_rate"],
                        "release_gate_passed": item["release_gate_passed"],
                        "unsafe_promoted": item["unsafe_promoted_count"],
                    }
                    for item in audit["scenario_summary"]
                },
                "downstream_unchanged": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


def audit_tv(db: Any) -> dict[str, Any]:
    version = current_published_version(db)
    if version is None:
        raise RuntimeError("TV has no current published M12D version")
    persisted_profiles = current_profiles(db, version.purchase_reason_version_id)
    source_batch_ids = tuple(str(item) for item in (version.source_batch_ids_json or ()) if str(item))
    read_scope = f"serving-scope:TV:{','.join(source_batch_ids)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        product_category=CATEGORY,
    )
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=CATEGORY)
    )
    generator = AnchorCandidateGenerator(taxonomy)
    evidence_scorer = EvidenceStrengthScorer()
    role_classifier = ReasonRoleClassifier()
    profile_scorer = ProfileConfidenceScorer()

    profiles: dict[str, dict[str, Any]] = {}
    baseline_status_counts: Counter[str] = Counter()
    for persisted in persisted_profiles:
        sku_code = str(persisted.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=CATEGORY,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        candidates = {candidate.anchor_code: candidate for candidate in candidate_set.purchase_reason_candidates}
        pre_anchors = [
            role_classifier.classify(evidence_scorer.score(candidate, context))
            for candidate in candidate_set.purchase_reason_candidates
        ]
        pre_anchors.sort(key=lambda item: (item.anchor_rank, item.anchor_code))
        final = profile_scorer.score(
            candidate_set=candidate_set,
            context=context,
            scored_anchors=pre_anchors,
        )
        market = dict(context.market_profile.summary)
        profile = {
            "sku_code": sku_code,
            "display_name_cn": context.display_name_cn,
            "market": {
                "price_wavg": market.get("price_wavg"),
                "price_latest": market.get("price_latest"),
                "sales_volume_total": market.get("sales_volume_total"),
                "screen_size_inch": market.get("screen_size_inch"),
                "size_segment": market.get("size_segment"),
                "price_band_category": market.get("price_band_category"),
                "price_band_size": market.get("price_band_size"),
            },
            "baseline": {
                "status": str(final.status),
                "profile_confidence": str(final.profile_confidence),
                "core_anchors": list(final.core_payment_anchors_json),
                "supporting_anchors": list(final.supporting_anchors_json),
                "weak_anchors": list(final.weak_expression_anchors_json),
                "risk_anchors": list(final.risk_drag_anchors_json),
            },
            "anchors": [
                anchor_audit_payload(anchor, candidates[anchor.anchor_code]) for anchor in pre_anchors
            ],
        }
        profiles[sku_code] = profile
        baseline_status_counts[str(final.status)] += 1

    attach_comment_alignment(db, profiles)

    scenario_results: dict[str, dict[str, dict[str, Any]]] = {}
    scenario_summary: list[dict[str, Any]] = []
    baseline_core_by_sku = {
        sku: tuple(profile["baseline"]["core_anchors"]) for sku, profile in profiles.items()
    }
    no_core_skus = sorted(sku for sku, cores in baseline_core_by_sku.items() if not cores)
    for scenario in SCENARIOS:
        results = {
            sku: evaluate_profile(profile, scenario) for sku, profile in sorted(profiles.items())
        }
        scenario_results[scenario.code] = results
        scenario_summary.append(
            summarize_scenario(scenario, profiles, results, baseline_core_by_sku, no_core_skus)
        )

    no_core_audit = [
        build_no_core_sku_audit(
            profiles[sku_code],
            {scenario.code: scenario_results[scenario.code][sku_code] for scenario in SCENARIOS},
        )
        for sku_code in no_core_skus
    ]
    recommendation_counts = Counter(item["recommendation"] for item in no_core_audit)
    return {
        "scope": {
            "category": CATEGORY,
            "project_id": PROJECT_ID,
            "taxonomy_version": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
            "purchase_reason_version_id": version.purchase_reason_version_id,
            "source_batch_ids": list(source_batch_ids),
            "read_scope": read_scope,
            "method": "只读重算当前证据；不新增评论、不写数据库、不修改生产门槛。",
        },
        "baseline": {
            "sku_count": len(profiles),
            "status_counts": dict(sorted(baseline_status_counts.items())),
            "no_core_count": len(no_core_skus),
        },
        "scenario_summary": scenario_summary,
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "no_core_sku_audit": no_core_audit,
    }


def anchor_audit_payload(anchor: Any, candidate: Any) -> dict[str, Any]:
    reason = dict(anchor.role_reason_json)
    domains = sorted(str(value) for value in anchor.evidence_domains_json)
    return {
        "anchor_code": anchor.anchor_code,
        "anchor_cn": anchor.anchor_cn,
        "anchor_family_code": anchor.anchor_family_code,
        "anchor_rank": int(anchor.anchor_rank),
        "baseline_role": str(anchor.role),
        "evidence_strength": str(anchor.evidence_strength),
        "confidence": str(anchor.confidence),
        "adjusted_evidence_score": str(anchor.adjusted_evidence_score),
        "strong_domain_count": len(set(domains) & STRONG_DOMAINS),
        "evidence_domains": domains,
        "scene_fit": "semantic_scene" in domains
        or {"comment_perception", "market_acceptance"} <= set(domains),
        "candidate_role_cap": str(candidate.role_cap) if candidate.role_cap else None,
        "candidate_role_cap_reasons": list(candidate.role_cap_reasons),
        "quality_role_cap": reason.get("quality_role_cap"),
        "quality_confidence_penalty": str(reason.get("quality_confidence_penalty") or "0"),
        "quality_confidence_cap": reason.get("quality_confidence_cap"),
        "applied_quality_issues": list(reason.get("applied_quality_issues") or ()),
        "risk_flags": [str(flag) for flag in anchor.risk_flags_json],
        "downgrade_reason_code": anchor.downgrade_reason_code,
        "support_summary_cn": anchor.support_summary_cn,
        "weakness_summary_cn": anchor.weakness_summary_cn,
        "source_ref_count": len(anchor.source_refs_json or ()),
        "source_refs": [compact_source_ref(ref) for ref in (anchor.source_refs_json or ())],
    }


def evaluate_profile(profile: Mapping[str, Any], scenario: Scenario) -> dict[str, Any]:
    if scenario.only_baseline_no_core and profile["baseline"]["core_anchors"]:
        return {
            "status": profile["baseline"]["status"],
            "core_anchors": list(profile["baseline"]["core_anchors"]),
            "profile_confidence": profile["baseline"]["profile_confidence"],
            "new_core_anchors": [],
            "selected_anchor_details": [],
        }
    eligible = [
        counterfactual_anchor(anchor, profile["market"], scenario)
        for anchor in profile["anchors"]
    ]
    eligible = [anchor for anchor in eligible if anchor["eligible"]]
    eligible.sort(key=counterfactual_sort_key)
    selected: list[dict[str, Any]] = []
    selected_families: set[str] = set()
    for anchor in eligible:
        family = str(anchor["anchor_family_code"] or anchor["anchor_code"])
        if family in selected_families:
            continue
        selected.append(anchor)
        selected_families.add(family)
        if len(selected) >= CORE_ANCHOR_LIMIT:
            break
    confidence = profile_confidence(selected)
    if selected:
        status = "ready" if confidence >= PROFILE_READY_CONFIDENCE else "ready_limited"
    else:
        status = str(profile["baseline"]["status"])
    return {
        "status": status,
        "core_anchors": [anchor["anchor_code"] for anchor in selected],
        "profile_confidence": str(q(confidence)),
        "new_core_anchors": [
            anchor["anchor_code"]
            for anchor in selected
            if anchor["anchor_code"] not in profile["baseline"]["core_anchors"]
        ],
        "selected_anchor_details": selected,
    }


def counterfactual_anchor(
    anchor: Mapping[str, Any], market: Mapping[str, Any], scenario: Scenario
) -> dict[str, Any]:
    flags = set(anchor["risk_flags"])
    failures: list[str] = []
    relaxed_gates: list[str] = []
    if anchor.get("candidate_role_cap") == "weak_expression":
        failures.append("candidate_weak_role_cap")
    if flags & HARD_RISK_FLAGS:
        failures.append("hard_risk")
    if anchor.get("quality_role_cap"):
        failures.append("input_quality_role_cap")
    if Decimal(anchor["adjusted_evidence_score"]) < scenario.strong_score_threshold:
        failures.append("score_below_threshold")
    if int(anchor["strong_domain_count"]) < 2:
        failures.append("strong_domain_count_below_2")
    if not anchor["scene_fit"]:
        failures.append("scene_fit_missing")
    if scenario.block_unsafe_evidence and flags & UNSAFE_EVIDENCE_FLAGS:
        failures.append("contradiction_negative_or_sample_risk")
    if (
        scenario.require_anchor_aligned_comment
        and "comment_perception" in anchor["evidence_domains"]
        and int(anchor.get("aligned_positive_comment_count") or 0) == 0
    ):
        failures.append("comment_domain_not_anchor_aligned")

    price_gate_missing = "price_value_core_evidence_missing" in flags
    if price_gate_missing:
        if scenario.relax_all_price_gate and anchor["anchor_code"] in PRICE_REASON_CODES:
            relaxed_gates.append("all_price_value_gate")
        elif (
            scenario.relax_objective_price_gate
            and anchor["anchor_code"] in OBJECTIVE_PRICE_REASON_CODES
            and objective_price_guard(anchor, market)
        ):
            relaxed_gates.append("objective_price_value_gate")
        else:
            failures.append("price_value_core_evidence_missing")

    confidence = strong_confidence(anchor)
    unsafe_reasons = unsafe_promotion_reasons(anchor, relaxed_gates, scenario)
    review_reasons = review_promotion_reasons(anchor, scenario)
    return {
        "anchor_code": anchor["anchor_code"],
        "anchor_cn": anchor["anchor_cn"],
        "anchor_family_code": anchor["anchor_family_code"],
        "anchor_rank": anchor["anchor_rank"],
        "adjusted_evidence_score": anchor["adjusted_evidence_score"],
        "strong_domain_count": anchor["strong_domain_count"],
        "evidence_domains": anchor["evidence_domains"],
        "risk_flags": anchor["risk_flags"],
        "aligned_positive_comment_count": anchor.get("aligned_positive_comment_count"),
        "aligned_positive_comment_examples": anchor.get("aligned_positive_comment_examples", []),
        "confidence": str(confidence),
        "eligible": not failures,
        "failed_gates": failures,
        "relaxed_gates": relaxed_gates,
        "unsafe_reasons": unsafe_reasons,
        "review_reasons": review_reasons,
    }


def objective_price_guard(anchor: Mapping[str, Any], market: Mapping[str, Any]) -> bool:
    flags = set(anchor["risk_flags"])
    domains = set(anchor["evidence_domains"])
    if anchor["anchor_code"] not in OBJECTIVE_PRICE_REASON_CODES:
        return False
    if not {"param_fact", "market_acceptance", "semantic_scene"} <= domains:
        return False
    if flags & (HARD_RISK_FLAGS | UNSAFE_EVIDENCE_FLAGS):
        return False
    if Decimal(str(market.get("sales_volume_total") or "0")) <= 0:
        return False
    if anchor["anchor_code"] == "low_price_core_experience_intact":
        price_bands = {
            str(market.get("price_band_category") or ""),
            str(market.get("price_band_size") or ""),
        }
        if not price_bands & {"low", "mid_low"}:
            return False
    return True


def unsafe_promotion_reasons(
    anchor: Mapping[str, Any], relaxed_gates: Sequence[str], scenario: Scenario
) -> list[str]:
    flags = set(anchor["risk_flags"])
    reasons: list[str] = []
    if flags & UNSAFE_EVIDENCE_FLAGS:
        reasons.append("contradiction_negative_or_sample_risk")
    if (
        "comment_perception" in anchor["evidence_domains"]
        and int(anchor.get("aligned_positive_comment_count") or 0) == 0
    ):
        reasons.append("comment_domain_not_anchor_aligned")
    if "all_price_value_gate" in relaxed_gates:
        reasons.append("subjective_and_objective_price_reasons_not_separated")
    return reasons


def review_promotion_reasons(anchor: Mapping[str, Any], scenario: Scenario) -> list[str]:
    if (
        scenario.strong_score_threshold < Decimal("9.0000")
        and Decimal(anchor["adjusted_evidence_score"]) < Decimal("9.0000")
    ):
        return ["strong_score_threshold_relaxed"]
    return []


def strong_confidence(anchor: Mapping[str, Any]) -> Decimal:
    confidence = Decimal("0.8500") - Decimal(str(anchor["quality_confidence_penalty"] or "0"))
    cap = anchor.get("quality_confidence_cap")
    if cap not in (None, ""):
        confidence = min(confidence, Decimal(str(cap)))
    return q(max(Decimal("0.0500"), min(Decimal("0.9500"), confidence)))


def counterfactual_sort_key(anchor: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -Decimal(anchor["adjusted_evidence_score"]),
        -Decimal(anchor["confidence"]),
        -int(anchor["strong_domain_count"]),
        int(anchor["anchor_rank"]),
        str(anchor["anchor_code"]),
    )


def profile_confidence(selected: Sequence[Mapping[str, Any]]) -> Decimal:
    if not selected:
        return Decimal("0.0000")
    weights = CORE_RANK_WEIGHTS[: len(selected)]
    total = sum(weights, Decimal("0"))
    return q(
        sum(
            (Decimal(anchor["confidence"]) * weight / total for anchor, weight in zip(selected, weights)),
            Decimal("0"),
        )
    )


def summarize_scenario(
    scenario: Scenario,
    profiles: Mapping[str, Mapping[str, Any]],
    results: Mapping[str, Mapping[str, Any]],
    baseline_core_by_sku: Mapping[str, Sequence[str]],
    no_core_skus: Sequence[str],
) -> dict[str, Any]:
    statuses = Counter(str(result["status"]) for result in results.values())
    promoted = [sku for sku in no_core_skus if results[sku]["core_anchors"]]
    unsafe_promoted = [
        sku
        for sku in promoted
        if any(
            detail["unsafe_reasons"] for detail in results[sku]["selected_anchor_details"]
        )
    ]
    review_promoted = [
        sku
        for sku in promoted
        if any(
            detail["review_reasons"] for detail in results[sku]["selected_anchor_details"]
        )
    ]
    existing_ready = [
        sku for sku, profile in profiles.items() if profile["baseline"]["status"] == "ready"
    ]
    changed_existing_ready = [
        sku
        for sku in existing_ready
        if tuple(results[sku]["core_anchors"]) != tuple(baseline_core_by_sku[sku])
    ]
    focus_changes = {
        sku: {
            "name": FOCUS_SKUS[sku],
            "before": list(baseline_core_by_sku.get(sku, ())),
            "after": list(results[sku]["core_anchors"]),
        }
        for sku in FOCUS_SKUS
        if sku in results
        and tuple(results[sku]["core_anchors"]) != tuple(baseline_core_by_sku.get(sku, ()))
    }
    total = len(results)
    ready = statuses.get("ready", 0)
    ready_limited = statuses.get("ready_limited", 0)
    no_core = sum(not result["core_anchors"] for result in results.values())
    release_gate_passed = (
        Decimal(ready) / total >= Decimal("0.85")
        and Decimal(ready + ready_limited) / total >= Decimal("0.95")
        and Decimal(no_core) / total <= Decimal("0.15")
    )
    return {
        "scenario_code": scenario.code,
        "scenario_name_cn": scenario.name_cn,
        "intended_safety": scenario.intended_safety,
        "status_counts": dict(sorted(statuses.items())),
        "no_core_count": no_core,
        "no_core_promoted_count": len(promoted),
        "no_core_promoted_skus": promoted,
        "unsafe_promoted_count": len(unsafe_promoted),
        "unsafe_promoted_skus": unsafe_promoted,
        "review_promoted_count": len(review_promoted),
        "review_promoted_skus": review_promoted,
        "existing_ready_core_changed_count": len(changed_existing_ready),
        "existing_ready_core_changed_skus": changed_existing_ready,
        "focus_sku_changes": focus_changes,
        "ready_rate": str(q(Decimal(ready) / total)),
        "ready_or_limited_rate": str(q(Decimal(ready + ready_limited) / total)),
        "no_core_rate": str(q(Decimal(no_core) / total)),
        "release_gate_passed": release_gate_passed,
    }


def build_no_core_sku_audit(
    profile: Mapping[str, Any], results: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    anchors = list(profile["anchors"])
    best = sorted(
        anchors,
        key=lambda item: (
            -Decimal(item["adjusted_evidence_score"]),
            -int(item["strong_domain_count"]),
            int(item["anchor_rank"]),
        ),
    )[0]
    bounded = results["guarded_score_8_no_core_only"]
    combined = results["objective_price_plus_score_8_5"]
    score_only = results["score_8_5_only"]
    safe_bounded = bool(bounded["core_anchors"]) and not any(
        detail["unsafe_reasons"] for detail in bounded["selected_anchor_details"]
    )
    if safe_bounded:
        recommendation = "可谨慎放宽"
        reason_cn = "8 分证据已满足双强证据域和场景门槛，且逐锚点排除了评论冲突、M12C 负向和市场样本风险。"
    elif combined["core_anchors"] or score_only["core_anchors"]:
        recommendation = "需人工抽检"
        reason_cn = "只有降低强证据分数后才能形成核心理由，现有证据不能自动证明不会误判。"
    else:
        recommendation = "不应放宽"
        reason_cn = "缺口涉及证据域、场景、风险或主观支付意愿，降低统一门槛会越过证据边界。"
    return {
        "sku_code": profile["sku_code"],
        "display_name_cn": profile["display_name_cn"],
        "market": profile["market"],
        "baseline_status": profile["baseline"]["status"],
        "best_anchor": {
            "anchor_code": best["anchor_code"],
            "anchor_cn": best["anchor_cn"],
            "baseline_role": best["baseline_role"],
            "adjusted_evidence_score": best["adjusted_evidence_score"],
            "strong_domain_count": best["strong_domain_count"],
            "evidence_domains": best["evidence_domains"],
            "scene_fit": best["scene_fit"],
            "risk_flags": best["risk_flags"],
            "downgrade_reason_code": best["downgrade_reason_code"],
        },
        "scenario_outcomes": {
            code: {
                "status": result["status"],
                "core_anchors": result["core_anchors"],
                "new_core_anchors": result["new_core_anchors"],
                "unsafe_reasons": sorted(
                    {
                        reason
                        for detail in result["selected_anchor_details"]
                        for reason in detail["unsafe_reasons"]
                    }
                ),
                "review_reasons": sorted(
                    {
                        reason
                        for detail in result["selected_anchor_details"]
                        for reason in detail["review_reasons"]
                    }
                ),
                "selected_anchor_details": [
                    {
                        "anchor_code": detail["anchor_code"],
                        "anchor_cn": detail["anchor_cn"],
                        "adjusted_evidence_score": detail["adjusted_evidence_score"],
                        "evidence_domains": detail["evidence_domains"],
                        "risk_flags": detail["risk_flags"],
                        "aligned_positive_comment_count": detail[
                            "aligned_positive_comment_count"
                        ],
                        "aligned_positive_comment_examples": detail[
                            "aligned_positive_comment_examples"
                        ],
                    }
                    for detail in result["selected_anchor_details"]
                ],
            }
            for code, result in results.items()
        },
        "recommendation": recommendation,
        "recommendation_reason_cn": reason_cn,
        "anchors": [compact_output_anchor(anchor) for anchor in anchors],
    }


def assert_baseline(audit: Mapping[str, Any]) -> None:
    baseline = audit["baseline"]
    failures = []
    if baseline["sku_count"] != EXPECTED_SKU_COUNT:
        failures.append(f"sku_count={baseline['sku_count']}")
    if baseline["status_counts"] != EXPECTED_BASELINE_STATUS:
        failures.append(f"status_counts={baseline['status_counts']}")
    if baseline["no_core_count"] != EXPECTED_NO_CORE_COUNT:
        failures.append(f"no_core_count={baseline['no_core_count']}")
    baseline_scenario = next(
        item for item in audit["scenario_summary"] if item["scenario_code"] == "baseline"
    )
    if baseline_scenario["no_core_promoted_count"] != 0:
        failures.append("counterfactual baseline promoted no-core SKU")
    if baseline_scenario["existing_ready_core_changed_count"] != 0:
        failures.append("counterfactual baseline changed existing ready cores")
    if failures:
        raise RuntimeError("QF15A baseline mismatch: " + "; ".join(failures))


def render_markdown(audit: Mapping[str, Any]) -> str:
    baseline = audit["baseline"]
    lines = [
        "# M12D-QF-15A TV 139 个无核心 SKU 证据缺口与门槛反事实审计",
        "",
        f"- 生成时间：`{audit['generated_at']}`",
        "- 口径：沿用 QF15 当前真实参数、卖点、评论、市场和语义证据，只读重算。",
        "- 禁止项：未补造评论、未修改生产评分、未写数据库、未发布 current、未运行竞品智能体。",
        f"- 基线：TV `{baseline['sku_count']}` 个；状态 `{baseline['status_counts']}`；无核心 `{baseline['no_core_count']}` 个。",
        "",
        "## 1. 反事实测算",
        "",
        "| 方案 | 新增核心 SKU | 其中证据越界 | 需抽检 | ready率 | ready+limited率 | 无核心率 | 改动既有 ready 核心 | 重点 SKU 变化 | 过发布门槛 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in audit["scenario_summary"]:
        lines.append(
            f"| {item['scenario_name_cn']} | {item['no_core_promoted_count']} | "
            f"{item['unsafe_promoted_count']} | {item['review_promoted_count']} | {item['ready_rate']} | "
            f"{item['ready_or_limited_rate']} | {item['no_core_rate']} | "
            f"{item['existing_ready_core_changed_count']} | {len(item['focus_sku_changes'])} | "
            f"{'是' if item['release_gate_passed'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## 2. 审计结论",
            "",
            f"- 逐 SKU 建议分布：`{audit['recommendation_counts']}`。",
            "- `可谨慎放宽` 使用无核心画像专属的 8 分兜底：仍要求至少两个强证据域和场景成立，价格理由仍保留现行支付证据门槛，并逐锚点排除评论冲突、M12C 负向和市场样本不足。",
            "- 评论感知必须在 M05C 原始事实中存在与购买理由同维度的正向评论；泛化好评、服务评论或其他体验维度不能替代。",
            "- 单独放宽客观性价比价格门槛新增 0 个 SKU，因此没有必要修改价格门槛。",
            "- 画质升级值不值、是否愿意多付等主观支付理由仍要求 M12C，或评论感知与市场承接同时成立，不能用参数和销量替代用户支付意愿。",
            "- 单纯把强证据分数从 9.0 降到 8.5/8.0 的新增结果标记为人工抽检，不自动判定安全。",
            "- 任何包含真实拖累、评论冲突、M12C 负向或样本不足的新增核心均计为证据越界。",
            "",
            "## 3. 可谨慎放宽 SKU",
            "",
            "| SKU | 产品 | 当前状态 | 放宽后核心理由 | 入选分数 | 入选证据域 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in audit["no_core_sku_audit"]:
        if row["recommendation"] != "可谨慎放宽":
            continue
        outcome = row["scenario_outcomes"]["guarded_score_8_no_core_only"]
        selected = outcome["selected_anchor_details"]
        scores = sorted({item["adjusted_evidence_score"] for item in selected})
        domains = sorted({domain for item in selected for domain in item["evidence_domains"]})
        lines.append(
            f"| {row['sku_code']} | {row['display_name_cn']} | {row['baseline_status']} | "
            f"{join_values(outcome['core_anchors'])} | {join_values(scores)} | "
            f"{join_values(domains)} |"
        )
    lines.extend(
        [
            "",
            "## 4. 边界说明",
            "",
            "- JSON 保留 139 个 SKU 的全部候选理由、证据域、分数、风险标记和各方案结果。",
            "- CSV 提供逐 SKU 主结论，便于业务抽检。",
            "- 本审计只回答门槛可否放宽，不代表 QF15 已解除阻塞；生产改动必须另立任务并通过抽检回归。",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "sku_code",
        "display_name_cn",
        "baseline_status",
        "recommendation",
        "recommendation_reason_cn",
        "best_anchor_code",
        "best_anchor_cn",
        "best_adjusted_score",
        "best_strong_domain_count",
        "best_evidence_domains",
        "best_risk_flags",
        "objective_price_gate_core_anchors",
        "guarded_score_8_core_anchors",
        "score_8_5_core_anchors",
        "objective_price_plus_score_8_5_core_anchors",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            best = row["best_anchor"]
            outcomes = row["scenario_outcomes"]
            writer.writerow(
                {
                    "sku_code": row["sku_code"],
                    "display_name_cn": row["display_name_cn"],
                    "baseline_status": row["baseline_status"],
                    "recommendation": row["recommendation"],
                    "recommendation_reason_cn": row["recommendation_reason_cn"],
                    "best_anchor_code": best["anchor_code"],
                    "best_anchor_cn": best["anchor_cn"],
                    "best_adjusted_score": best["adjusted_evidence_score"],
                    "best_strong_domain_count": best["strong_domain_count"],
                    "best_evidence_domains": join_values(best["evidence_domains"]),
                    "best_risk_flags": join_values(best["risk_flags"]),
                    "objective_price_gate_core_anchors": join_values(
                        outcomes["objective_price_gate_only"]["core_anchors"]
                    ),
                    "guarded_score_8_core_anchors": join_values(
                        outcomes["guarded_score_8_no_core_only"]["core_anchors"]
                    ),
                    "score_8_5_core_anchors": join_values(
                        outcomes["score_8_5_only"]["core_anchors"]
                    ),
                    "objective_price_plus_score_8_5_core_anchors": join_values(
                        outcomes["objective_price_plus_score_8_5"]["core_anchors"]
                    ),
                }
            )


def compact_source_ref(ref: Any) -> dict[str, Any]:
    def value(key: str) -> Any:
        if isinstance(ref, Mapping):
            return ref.get(key)
        return getattr(ref, key, None)

    evidence_ids = value("evidence_ids") or ()
    extra = value("extra") or {}
    rule_version = extra.get("rule_version") if isinstance(extra, Mapping) else None
    return {
        "module_code": value("module_code"),
        "table_name": value("table_name"),
        "record_id": value("record_id"),
        "result_hash": value("result_hash"),
        "evidence_count": len(evidence_ids),
        "rule_version": rule_version,
    }


def compact_output_anchor(anchor: Mapping[str, Any]) -> dict[str, Any]:
    refs = list(anchor.get("source_refs") or ())
    module_counts = Counter(str(ref.get("module_code") or "unknown") for ref in refs)
    table_counts = Counter(str(ref.get("table_name") or "unknown") for ref in refs)
    result = dict(anchor)
    result.pop("source_refs", None)
    result["source_ref_summary"] = {
        "count": len(refs),
        "module_counts": dict(sorted(module_counts.items())),
        "table_counts": dict(sorted(table_counts.items())),
        "record_id_samples": [ref.get("record_id") for ref in refs[:5] if ref.get("record_id")],
    }
    return result


def attach_comment_alignment(
    db: Any, profiles: Mapping[str, dict[str, Any]]
) -> None:
    target_anchors = [
        anchor
        for profile in profiles.values()
        if not profile["baseline"]["core_anchors"]
        for anchor in profile["anchors"]
        if "comment_perception" in anchor["evidence_domains"]
    ]
    comment_ids = sorted(
        {
            ref["record_id"]
            for anchor in target_anchors
            for ref in anchor["source_refs"]
            if ref["table_name"] == "core3_comment_fact_atom" and ref["record_id"]
        }
    )
    facts: dict[str, Mapping[str, Any]] = {}
    for start in range(0, len(comment_ids), 2000):
        rows = db.execute(
            text(
                "SELECT comment_fact_id, dimension_code, subdimension_code, polarity, "
                "raw_comment_text FROM core3_comment_fact_atom "
                "WHERE comment_fact_id = ANY(CAST(:comment_ids AS varchar[]))"
            ),
            {"comment_ids": comment_ids[start : start + 2000]},
        ).mappings()
        facts.update({str(row["comment_fact_id"]): row for row in rows})
    for anchor in target_anchors:
        matched = [
            facts[ref["record_id"]]
            for ref in anchor["source_refs"]
            if ref["table_name"] == "core3_comment_fact_atom"
            and ref["record_id"] in facts
            and comment_fact_aligns(anchor["anchor_code"], facts[ref["record_id"]])
        ]
        anchor["aligned_positive_comment_count"] = len(matched)
        anchor["aligned_positive_comment_examples"] = [
            " ".join(str(row["raw_comment_text"] or "").split())[:160] for row in matched[:3]
        ]


def comment_fact_aligns(anchor_code: str, fact: Mapping[str, Any]) -> bool:
    if str(fact.get("polarity")) != "positive":
        return False
    dimension = str(fact.get("dimension_code") or "")
    subdimension = str(fact.get("subdimension_code") or "")
    if anchor_code == "gaming_device_fit_reduces_risk":
        return dimension == "gaming_motion_experience"
    if anchor_code == "sports_motion_stability":
        return dimension == "gaming_motion_experience"
    if anchor_code in {"living_room_upgrade_one_step", "big_screen_cinema_substitution"}:
        return (
            (dimension == "use_case_signal" and subdimension == "use_living_room_cinema")
            or (dimension == "appearance_installation_space" and subdimension == "appearance_size_fit")
            or dimension == "audio_cinema_experience"
        )
    if anchor_code in {"low_price_core_experience_intact", "same_price_core_config_gain"}:
        return dimension == "price_value_perception"
    if anchor_code in SUBJECTIVE_PRICE_REASON_CODES:
        return dimension == "picture_screen_experience"
    return True


def current_published_version(db: Any) -> Any:
    return db.execute(
        text(
            "SELECT purchase_reason_version_id, source_batch_ids_json "
            "FROM core3_purchase_reason_profile_version "
            "WHERE project_id = :project_id AND category_code = :category "
            "AND product_category = :category AND release_status = 'published' "
            "AND is_current IS TRUE ORDER BY published_at DESC LIMIT 1"
        ),
        {"project_id": PROJECT_ID, "category": CATEGORY},
    ).first()


def current_profiles(db: Any, version_id: str) -> list[Any]:
    return list(
        db.execute(
            text(
                "SELECT sku_code FROM core3_sku_purchase_reason_profile "
                "WHERE project_id = :project_id AND category_code = :category "
                "AND product_category = :category AND purchase_reason_version_id = :version_id "
                "AND is_current IS TRUE ORDER BY sku_code"
            ),
            {"project_id": PROJECT_ID, "category": CATEGORY, "version_id": version_id},
        )
    )


def capture_guard(db: Any) -> dict[str, dict[str, Any]]:
    result = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table_name}")
        ).one()
        result[table_name] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def join_values(values: Iterable[Any]) -> str:
    result = [str(value) for value in values if str(value)]
    return "、".join(result) if result else "-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-csv", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
