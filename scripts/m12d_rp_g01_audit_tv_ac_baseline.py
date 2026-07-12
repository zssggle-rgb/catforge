#!/usr/bin/env python3
"""Read-only TV/AC baseline for separating reason establishment from pressure."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
    DOMAIN_MAX_SCORES,
    STRONG_EVIDENCE_DOMAINS,
    EvidenceStrengthScorer,
    ProfileConfidenceScorer,
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
PRESSURE_FLAGS = {
    "comment_claim_contradiction",
    "comment_negative_dominates",
    "m12c_related_claim_negative",
    "claim_value_drag_factor",
}
POSITIVE_M12C_ROLES = {
    "sales_driver_estimated",
    "premium_driver_estimated",
    "sales_driver",
    "premium_driver",
}
OBJECTIVE_BLOCK_FLAGS = {
    "m03b_true_param_conflict",
    "anchor_quality_blocking",
}
MARKET_LIMIT_PREFIXES = ("market_pool_", "price_band_sample_", "size_pool_")
TV_REFERENCE_COUNTS = {
    "no_core": 139,
    "guarded_reason_established": 37,
    "ordinary_pressure": 29,
    "proposition_only": 29,
}

# A comment can support an anchor only through one of these business dimensions.
# Missing mappings are rejected rather than treated as an automatic match.
COMMENT_DIMENSIONS: dict[str, dict[str, set[tuple[str, str | None]]]] = {
    "TV": {
        "picture_upgrade_justifies_price": {("picture_screen_experience", None)},
        "low_price_core_experience_intact": {("price_value_perception", None)},
        "same_price_core_config_gain": {("price_value_perception", None)},
        "same_size_picture_step_up": {("picture_screen_experience", None)},
        "worth_paying_more_for_experience_upgrade": {("picture_screen_experience", None)},
        "av_user_willing_to_pay_for_picture": {("picture_screen_experience", None)},
        "gaming_device_fit_reduces_risk": {
            ("gaming_motion_experience", None),
            ("use_case_signal", "use_gaming_sports"),
        },
        "sports_motion_stability": {
            ("gaming_motion_experience", None),
            ("use_case_signal", "use_gaming_sports"),
        },
        "big_screen_cinema_substitution": {
            ("use_case_signal", "use_living_room_cinema"),
            ("appearance_installation_space", "appearance_size_fit"),
            ("audio_cinema_experience", None),
        },
        "living_room_upgrade_one_step": {
            ("use_case_signal", "use_living_room_cinema"),
            ("appearance_installation_space", "appearance_size_fit"),
            ("audio_cinema_experience", None),
        },
        "family_long_watch_comfort_assurance": {
            ("picture_screen_experience", "picture_eye_care_reflection"),
            ("use_case_signal", "use_bedroom"),
            ("audience_signal", "audience_child_family"),
            ("audience_signal", "audience_senior"),
        },
        "family_operation_less_friction": {("system_interaction_experience", None)},
        "new_home_aesthetic_fit": {("appearance_installation_space", None)},
    },
    "AC": {
        "room_size_capacity_match_reduces_risk": {
            ("temperature_effect_experience", None),
            ("appearance_installation_space", "space_fit_area"),
        },
        "large_space_one_step_cooling_heating": {
            ("temperature_effect_experience", None),
            ("airflow_comfort_experience", "airflow_volume_coverage"),
            ("use_case_signal", "use_living_room_large"),
        },
        "cooling_heating_performance_justifies_price": {
            ("temperature_effect_experience", None),
            ("price_value_perception", None),
        },
        "long_term_energy_saving_offsets_price": {
            ("energy_cost_experience", None),
            ("price_value_perception", None),
        },
        "same_price_efficiency_capacity_gain": {
            ("price_value_perception", None),
            ("energy_cost_experience", None),
            ("temperature_effect_experience", None),
        },
        "low_price_core_ac_experience_intact": {
            ("price_value_perception", None),
            ("temperature_effect_experience", None),
        },
        "sleep_room_quiet_comfort_assurance": {
            ("noise_sleep_experience", None),
            ("use_case_signal", "use_bedroom_sleep"),
        },
        "elderly_child_soft_wind_comfort": {
            ("airflow_comfort_experience", "soft_wind_no_direct"),
            ("audience_signal", "audience_senior_parent"),
            ("audience_signal", "audience_child_baby"),
            ("audience_signal", "audience_family"),
        },
        "fresh_air_health_reduces_stuffy_risk": {("health_clean_air_experience", None)},
        "humidity_dehumidification_reassurance": {("health_clean_air_experience", None)},
        "self_cleaning_reduces_maintenance_risk": {
            ("health_clean_air_experience", "self_cleaning")
        },
        "small_room_installation_fit": {
            ("appearance_installation_space", None),
            ("use_case_signal", "use_bedroom_sleep"),
        },
        "smart_remote_control_less_friction": {("smart_control_experience", None)},
    },
}

OBJECTIVE_MARKET_REASON_CODES = {
    "TV": {
        "low_price_core_experience_intact",
        "same_price_core_config_gain",
        "same_size_picture_step_up",
        "big_screen_cinema_substitution",
        "living_room_upgrade_one_step",
    },
    "AC": {
        "room_size_capacity_match_reduces_risk",
        "large_space_one_step_cooling_heating",
        "long_term_energy_saving_offsets_price",
        "same_price_efficiency_capacity_gain",
        "low_price_core_ac_experience_intact",
        "small_room_installation_fit",
    },
}


def main() -> int:
    args = parse_args()
    outputs = [Path(value) for value in (args.output_json, args.output_csv, args.output_markdown, args.output_fixture)]
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        before = capture_guard(db)
        categories = {category: audit_category(db, category) for category in ("TV", "AC")}
        after = capture_guard(db)
    if before != after:
        raise RuntimeError("M12D-RP-G01 read-only audit changed persisted M12D tables")

    payload = {
        "task_id": "M12D-RP-G01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "method": {
            "current_result": "使用当前 M12D 生产评分只读重算，保留现行结果作为基线。",
            "audit_result": "成立分只读取同锚点正向证据；普通负面和 M12C 负向单列压力，不从成立分扣除。",
            "warning": "G01 是审计口径和影响集合，不是已上线算法；G02-G05 才实现 typed contract 和生产逻辑。",
        },
        "categories": categories,
        "downstream_guard": {"before": before, "after": after, "unchanged": before == after},
    }
    fixture = build_fixture(payload)
    payload["acceptance"] = build_acceptance(payload, fixture)
    write_json(outputs[0], payload)
    write_csv(outputs[1], payload)
    outputs[2].write_text(render_markdown(payload, fixture), encoding="utf-8")
    write_json(outputs[3], fixture)
    if not payload["acceptance"]["passed"]:
        raise RuntimeError("G01 acceptance failed: " + ", ".join(payload["acceptance"]["failed_checks"]))
    print(json.dumps({
        "status": "ok",
        "categories": {
            category: data["counts"] for category, data in categories.items()
        },
        "downstream_unchanged": True,
    }, ensure_ascii=False))
    return 0


def audit_category(db: Any, category: str) -> dict[str, Any]:
    version = current_published_version(db, category)
    if version is None:
        raise RuntimeError(f"{category} has no current published M12D version")
    persisted = current_profiles(db, category, version.purchase_reason_version_id)
    source_batch_ids = tuple(str(value) for value in (version.source_batch_ids_json or ()) if str(value))
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(CATEGORY_TAXONOMY[category], product_category=category)
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    )
    generator = AnchorCandidateGenerator(taxonomy)
    evidence_scorer = EvidenceStrengthScorer()
    role_classifier = ReasonRoleClassifier()
    profile_scorer = ProfileConfidenceScorer()

    profiles: list[dict[str, Any]] = []
    comment_ids: set[str] = set()
    for row in persisted:
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=str(row.sku_code),
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        candidates = {candidate.anchor_code: candidate for candidate in candidate_set.purchase_reason_candidates}
        anchors = [
            role_classifier.classify(evidence_scorer.score(candidate, context))
            for candidate in candidate_set.purchase_reason_candidates
        ]
        anchors.sort(key=lambda value: (value.anchor_rank, value.anchor_code))
        final = profile_scorer.score(candidate_set=candidate_set, context=context, scored_anchors=anchors)
        compact_anchors = []
        for anchor in anchors:
            compact = compact_anchor(
                anchor,
                candidates[anchor.anchor_code],
                context.claim_value_profile.summary,
            )
            compact_anchors.append(compact)
            comment_ids.update(compact["_comment_ids"])
        profiles.append({
            "sku_code": str(row.sku_code),
            "display_name_cn": context.display_name_cn,
            "market": compact_market(context.market_profile.summary, category),
            "current": {
                "status": str(final.status),
                "profile_confidence": str(final.profile_confidence),
                "core_anchors": list(final.core_payment_anchors_json),
                "supporting_anchors": list(final.supporting_anchors_json),
                "weak_anchors": list(final.weak_expression_anchors_json),
                "risk_anchors": list(final.risk_drag_anchors_json),
            },
            "anchors": compact_anchors,
        })

    facts = load_comment_facts(db, comment_ids)
    for profile in profiles:
        for anchor in profile["anchors"]:
            attach_comment_evidence(category, anchor, facts)
            classify_anchor(category, profile, anchor)
        summarize_profile(profile)

    profile_counts = Counter(profile["current"]["status"] for profile in profiles)
    no_core = sorted(profile["sku_code"] for profile in profiles if not profile["current"]["core_anchors"])
    impact_sets = build_impact_sets(profiles, no_core)
    unaffected = [
        compact_regression(profile)
        for profile in profiles
        if current_core_unaffected(profile)
    ][:20]
    return {
        "category": category,
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "source_batch_ids": list(source_batch_ids),
        "read_scope": read_scope,
        "counts": {
            "sku_count": len(profiles),
            "current_status_counts": dict(sorted(profile_counts.items())),
            "current_no_core": len(no_core),
            **{key: len(value) for key, value in impact_sets.items()},
        },
        "reference_check": (
            {key: {"expected": expected, "observed": len(impact_sets[key]), "matches": expected == len(impact_sets[key])}
             for key, expected in TV_REFERENCE_COUNTS.items()}
            if category == "TV" else {"note": "AC 独立形成基线，不使用 TV 数字作目标。"}
        ),
        "impact_sets": impact_sets,
        "unaffected_regression_samples": unaffected,
        "profiles": profiles,
    }


def compact_anchor(
    anchor: Any,
    candidate: Any,
    claim_value_summary: Mapping[str, Any],
) -> dict[str, Any]:
    reason = dict(anchor.role_reason_json)
    domains = sorted(str(value) for value in anchor.evidence_domains_json)
    refs = [compact_source_ref(ref) for ref in (anchor.source_refs_json or ())]
    return {
        "anchor_code": anchor.anchor_code,
        "anchor_cn": anchor.anchor_cn,
        "anchor_family_code": anchor.anchor_family_code,
        "anchor_rank": int(anchor.anchor_rank),
        "current_role": str(anchor.role),
        "current_strength": str(anchor.evidence_strength),
        "current_confidence": str(anchor.confidence),
        "raw_evidence_score": str(anchor.raw_evidence_score),
        "adjusted_evidence_score": str(anchor.adjusted_evidence_score),
        "strong_domain_count": len(set(domains) & {str(value) for value in STRONG_EVIDENCE_DOMAINS}),
        "evidence_domains": domains,
        "scene_fit": "semantic_scene" in domains or {"comment_perception", "market_acceptance"} <= set(domains),
        "risk_flags": [str(flag) for flag in anchor.risk_flags_json],
        "m12c_roles": anchor_claim_value_roles(claim_value_summary, anchor.anchor_code),
        "applied_quality_issues": list(reason.get("applied_quality_issues") or ()),
        "candidate_role_cap": str(candidate.role_cap) if candidate.role_cap else None,
        "support_summary_cn": anchor.support_summary_cn,
        "source_ref_summary": summarize_refs(refs),
        "_comment_ids": [
            ref["record_id"] for ref in refs
            if ref["table_name"] == "core3_comment_fact_atom" and ref["record_id"]
        ],
    }


def attach_comment_evidence(category: str, anchor: dict[str, Any], facts: Mapping[str, Mapping[str, Any]]) -> None:
    ids = anchor.pop("_comment_ids", [])
    matched = [facts[value] for value in ids if value in facts and comment_aligns(category, anchor["anchor_code"], facts[value])]
    polarity = Counter(str(item.get("polarity") or "unknown") for item in matched)
    positive = polarity["positive"]
    negative = polarity["negative"]
    mixed = polarity["mixed"]
    anchor["comment_alignment"] = {
        "referenced_count": len(ids),
        "aligned_count": len(matched),
        "positive_count": positive,
        "negative_count": negative,
        "mixed_count": mixed,
        "wrong_dimension": "comment_perception" in anchor["evidence_domains"] and positive == 0,
        "examples": [
            {
                "comment_fact_id": str(item["comment_fact_id"]),
                "dimension_code": str(item["dimension_code"]),
                "subdimension_code": str(item["subdimension_code"]),
                "polarity": str(item["polarity"]),
                "text": " ".join(str(item.get("raw_comment_text") or "").split())[:160],
            }
            for item in matched[:4]
        ],
    }


def classify_anchor(category: str, profile: Mapping[str, Any], anchor: dict[str, Any]) -> None:
    domains = set(anchor["evidence_domains"])
    flags = set(anchor["risk_flags"])
    issue_codes = {
        str(issue.get("issue_code"))
        for issue in anchor["applied_quality_issues"]
        if issue.get("applied")
    }
    comment = anchor["comment_alignment"]
    has_product = bool(domains & {"param_fact", "fact_claim"})
    aligned_positive = int(comment["positive_count"]) > 0
    positive_m12c = bool(set(anchor["m12c_roles"]) & POSITIVE_M12C_ROLES)
    market = "market_acceptance" in domains
    objective_market = anchor["anchor_code"] in OBJECTIVE_MARKET_REASON_CODES[category]
    if aligned_positive and (market or positive_m12c):
        validation = "user_validated"
    elif aligned_positive and (has_product or anchor["scene_fit"]):
        validation = "user_supported"
    elif positive_m12c and (has_product or anchor["scene_fit"]):
        validation = "user_supported"
    elif objective_market and market and has_product and anchor["scene_fit"]:
        validation = "market_supported"
    elif has_product and anchor["scene_fit"]:
        validation = "proposition_only"
    else:
        validation = "rejected"

    establishment_score = Decimal(anchor["raw_evidence_score"])
    establishment_domains = set(domains)
    if "comment_perception" in domains and not aligned_positive:
        establishment_score -= DOMAIN_MAX_SCORES[next(value for value in DOMAIN_MAX_SCORES if value.value == "comment_perception")]
        establishment_domains.discard("comment_perception")
    if "claim_value" in domains and not positive_m12c:
        establishment_score -= DOMAIN_MAX_SCORES[next(value for value in DOMAIN_MAX_SCORES if value.value == "claim_value")]
        establishment_domains.discard("claim_value")
    establishment_score = max(Decimal("0"), establishment_score)
    establishment_strong_domain_count = len(
        establishment_domains & {str(value) for value in STRONG_EVIDENCE_DOMAINS}
    )
    objective_falsification = bool((flags | issue_codes) & OBJECTIVE_BLOCK_FLAGS)
    evidence_misalignment = bool(comment["wrong_dimension"])
    business_boundary = reason_business_boundary(category, profile, anchor, validation)
    threshold = None
    current_no_core = not profile["current"]["core_anchors"]
    if establishment_score >= 9 and establishment_strong_domain_count >= 2 and anchor["scene_fit"] and validation in {"user_supported", "user_validated"}:
        threshold = "standard_9"
    elif current_no_core and establishment_score >= 8 and establishment_strong_domain_count >= 2 and anchor["scene_fit"] and validation in {"user_supported", "user_validated", "market_supported"} and business_boundary:
        threshold = "no_core_8"
    elif current_no_core and establishment_score >= 7 and establishment_strong_domain_count >= 2 and anchor["scene_fit"] and validation in {"user_supported", "user_validated", "market_supported"} and business_boundary:
        threshold = "reason_specific_7"
    established = bool(threshold) and not objective_falsification

    weighted_negative = int(comment["negative_count"]) + Decimal("0.5") * int(comment["mixed_count"])
    pressure_labels: list[str] = []
    if int(comment["negative_count"]) > 0 and int(comment["positive_count"]) >= weighted_negative:
        pressure_labels.append("localized_negative")
    if int(comment["positive_count"]) > 0 and (int(comment["negative_count"]) > 0 or int(comment["mixed_count"]) > 0):
        pressure_labels.append("mixed_feedback")
    if weighted_negative > int(comment["positive_count"]):
        pressure_labels.append("negative_dominant")
    if flags & {"m12c_related_claim_negative", "claim_value_drag_factor"}:
        pressure_labels.append("m12c_value_headwind")
    if any(code.startswith(MARKET_LIMIT_PREFIXES) for code in flags | issue_codes):
        pressure_labels.append("market_uncertainty")
    if objective_falsification:
        pressure_labels.append("objective_falsification")
    if evidence_misalignment:
        pressure_labels.append("evidence_misalignment")
    anchor["audit"] = {
        "establishment_score": str(establishment_score.quantize(Decimal("0.0001"))),
        "establishment_domains": sorted(establishment_domains),
        "establishment_strong_domain_count": establishment_strong_domain_count,
        "user_validation": validation,
        "business_boundary_passed": business_boundary,
        "threshold_path": threshold,
        "established": established,
        "core_eligible": established and validation != "proposition_only",
        "pressure_labels": list(dict.fromkeys(pressure_labels)),
        "legacy_pressure_flags": sorted(flags & PRESSURE_FLAGS),
        "ordinary_pressure": bool(set(pressure_labels) & {"localized_negative", "mixed_feedback", "m12c_value_headwind"}),
        "objective_block": objective_falsification,
    }


def reason_business_boundary(category: str, profile: Mapping[str, Any], anchor: Mapping[str, Any], validation: str) -> bool:
    code = str(anchor["anchor_code"])
    market = profile["market"]
    comment = anchor["comment_alignment"]
    if validation == "proposition_only" or validation == "rejected":
        return False
    if category == "TV":
        if code == "big_screen_cinema_substitution":
            return decimal_value(market.get("screen_size_inch")) >= Decimal("75") and (comment["positive_count"] > 0 or "market_acceptance" in anchor["evidence_domains"])
        if code == "low_price_core_experience_intact":
            return market.get("price_band_category") in {"low", "mid_low"} and (comment["positive_count"] > 0 or "market_acceptance" in anchor["evidence_domains"])
        if code in {"picture_upgrade_justifies_price", "worth_paying_more_for_experience_upgrade", "av_user_willing_to_pay_for_picture"}:
            return market.get("price_band_size") in {"mid_high", "high"} and comment["positive_count"] > 0
        if code in {"gaming_device_fit_reduces_risk", "sports_motion_stability"}:
            return comment["positive_count"] > 0
        if code in {"family_operation_less_friction", "new_home_aesthetic_fit"}:
            return comment["positive_count"] > 0
        return True
    if code in {"room_size_capacity_match_reduces_risk", "large_space_one_step_cooling_heating"}:
        return comment["positive_count"] > 0 or "market_acceptance" in anchor["evidence_domains"]
    if code in {"cooling_heating_performance_justifies_price", "long_term_energy_saving_offsets_price", "same_price_efficiency_capacity_gain", "low_price_core_ac_experience_intact"}:
        return comment["positive_count"] > 0 or ("market_acceptance" in anchor["evidence_domains"] and validation == "market_supported")
    if code == "small_room_installation_fit":
        return comment["positive_count"] > 0 and any(item["dimension_code"] != "service_fulfillment_excluded" for item in comment["examples"])
    return comment["positive_count"] > 0


def summarize_profile(profile: dict[str, Any]) -> None:
    established = [anchor["anchor_code"] for anchor in profile["anchors"] if anchor["audit"]["established"]]
    proposition = [anchor["anchor_code"] for anchor in profile["anchors"] if anchor["audit"]["user_validation"] == "proposition_only"]
    pressures = sorted({label for anchor in profile["anchors"] for label in anchor["audit"]["pressure_labels"]})
    ordinary = any(anchor["audit"]["established"] and anchor["audit"]["ordinary_pressure"] for anchor in profile["anchors"])
    profile["audit_summary"] = {
        "established_anchors": established,
        "proposition_only_anchors": proposition,
        "pressure_labels": pressures,
        "established_with_ordinary_pressure": ordinary,
        "comment_wrong_dimension": any(anchor["comment_alignment"]["wrong_dimension"] for anchor in profile["anchors"]),
        "objective_block": any(anchor["audit"]["objective_block"] for anchor in profile["anchors"]),
    }


def build_impact_sets(profiles: Sequence[Mapping[str, Any]], no_core: Sequence[str]) -> dict[str, list[str]]:
    return {
        "no_core": sorted(no_core),
        "guarded_reason_established": sorted(profile["sku_code"] for profile in profiles if not profile["current"]["core_anchors"] and profile["audit_summary"]["established_anchors"] and not profile["audit_summary"]["established_with_ordinary_pressure"]),
        "ordinary_pressure": sorted(profile["sku_code"] for profile in profiles if not profile["current"]["core_anchors"] and profile["audit_summary"]["established_with_ordinary_pressure"]),
        "negative_dominant": sorted(profile["sku_code"] for profile in profiles if "negative_dominant" in profile["audit_summary"]["pressure_labels"]),
        "m12c_negative": sorted(profile["sku_code"] for profile in profiles if "m12c_value_headwind" in profile["audit_summary"]["pressure_labels"]),
        "proposition_only": sorted(profile["sku_code"] for profile in profiles if not profile["current"]["core_anchors"] and profile["audit_summary"]["proposition_only_anchors"] and not profile["audit_summary"]["established_anchors"]),
        "comment_wrong_dimension": sorted(profile["sku_code"] for profile in profiles if profile["audit_summary"]["comment_wrong_dimension"]),
        "objective_block": sorted(profile["sku_code"] for profile in profiles if profile["audit_summary"]["objective_block"]),
    }


def build_fixture(payload: Mapping[str, Any]) -> dict[str, Any]:
    fixture = {"task_id": "M12D-RP-G01", "generated_at": payload["generated_at"], "categories": {}}
    for category, data in payload["categories"].items():
        profiles = data["profiles"]
        buckets = {
            "positive_established": lambda p, a: a["audit"]["established"] and not a["audit"]["pressure_labels"],
            "localized_negative": lambda p, a: a["audit"]["established"] and "localized_negative" in a["audit"]["pressure_labels"],
            "negative_dominant": lambda p, a: "negative_dominant" in a["audit"]["pressure_labels"],
            "m12c_value_headwind": lambda p, a: "m12c_value_headwind" in a["audit"]["pressure_labels"],
            "proposition_only": lambda p, a: a["audit"]["user_validation"] == "proposition_only",
            "evidence_misalignment": lambda p, a: "evidence_misalignment" in a["audit"]["pressure_labels"],
            "objective_falsification": lambda p, a: "objective_falsification" in a["audit"]["pressure_labels"],
        }
        result = {}
        for name, predicate in buckets.items():
            matches = [compact_fixture(profile, anchor) for profile in profiles for anchor in profile["anchors"] if predicate(profile, anchor)]
            result[name] = {"observed_count": len(matches), "samples": matches[:5]}
            if not matches and name == "objective_falsification":
                result[name]["synthetic_contract_fixture"] = {
                    "fixture_kind": "synthetic_contract_only",
                    "reason": "真实基线未观察到可复用正例；用于 G02/G03 的确定性阻断测试，不形成业务结论。",
                    "input": {"positive_fact": True, "same_fact_objectively_falsified": True},
                    "expected": {"established": False, "pressure_labels": ["objective_falsification"]},
                }
        fixture["categories"][category] = result
    return fixture


def compact_fixture(profile: Mapping[str, Any], anchor: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fixture_kind": "observed",
        "sku_code": profile["sku_code"],
        "display_name_cn": profile["display_name_cn"],
        "anchor_code": anchor["anchor_code"],
        "anchor_cn": anchor["anchor_cn"],
        "audit": anchor["audit"],
        "comment_alignment": anchor["comment_alignment"],
        "source_ref_summary": anchor["source_ref_summary"],
    }


def build_acceptance(payload: Mapping[str, Any], fixture: Mapping[str, Any]) -> dict[str, Any]:
    failed = []
    for category, data in payload["categories"].items():
        if len(data["unaffected_regression_samples"]) < 20:
            failed.append(f"{category}_unaffected_samples_below_20")
        if data["counts"]["sku_count"] <= 0:
            failed.append(f"{category}_empty_scope")
        if not fixture["categories"][category]["positive_established"]["samples"]:
            failed.append(f"{category}_positive_fixture_missing")
        if not fixture["categories"][category]["proposition_only"]["samples"]:
            failed.append(f"{category}_proposition_fixture_missing")
    if not payload["downstream_guard"]["unchanged"]:
        failed.append("downstream_tables_changed")
    return {
        "passed": not failed,
        "failed_checks": failed,
        "checks": {
            "read_only_tables_unchanged": payload["downstream_guard"]["unchanged"],
            "unaffected_samples_per_category": {category: len(data["unaffected_regression_samples"]) for category, data in payload["categories"].items()},
            "reference_counts_are_diagnostics_not_quotas": True,
            "production_logic_changed": False,
        },
    }


def comment_aligns(category: str, anchor_code: str, fact: Mapping[str, Any]) -> bool:
    allowed = COMMENT_DIMENSIONS.get(category, {}).get(anchor_code, set())
    dimension = str(fact.get("dimension_code") or "")
    subdimension = str(fact.get("subdimension_code") or "")
    return any(dimension == target and (sub is None or subdimension == sub) for target, sub in allowed)


def load_comment_facts(db: Any, comment_ids: Iterable[str]) -> dict[str, Mapping[str, Any]]:
    values = sorted(set(comment_ids))
    result: dict[str, Mapping[str, Any]] = {}
    for start in range(0, len(values), 2000):
        rows = db.execute(text(
            "SELECT comment_fact_id, dimension_code, subdimension_code, polarity, raw_comment_text "
            "FROM core3_comment_fact_atom WHERE comment_fact_id = ANY(CAST(:ids AS varchar[]))"
        ), {"ids": values[start:start + 2000]}).mappings()
        result.update({str(row["comment_fact_id"]): row for row in rows})
    return result


def anchor_claim_value_roles(summary: Mapping[str, Any], anchor_code: str) -> list[str]:
    anchor_roles = summary.get("anchor_claim_value_roles") or {}
    if not isinstance(anchor_roles, Mapping):
        return []
    claim_roles = anchor_roles.get(anchor_code) or {}
    if not isinstance(claim_roles, Mapping):
        return []
    roles: list[str] = []
    for value in claim_roles.values():
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            roles.extend(str(role) for role in value if str(role))
        elif value:
            roles.append(str(value))
    return sorted(set(roles))


def compact_market(summary: Mapping[str, Any], category: str) -> dict[str, Any]:
    keys = ["price_wavg", "price_latest", "sales_volume_total", "price_band_category", "price_band_size"]
    keys.extend(["screen_size_inch", "size_segment"] if category == "TV" else ["horsepower_segment", "form_type", "market_pool_code"])
    return {key: summary.get(key) for key in keys}


def compact_source_ref(ref: Any) -> dict[str, Any]:
    def value(key: str) -> Any:
        return ref.get(key) if isinstance(ref, Mapping) else getattr(ref, key, None)
    return {
        "module_code": value("module_code"),
        "table_name": value("table_name"),
        "record_id": value("record_id"),
        "result_hash": value("result_hash"),
    }


def summarize_refs(refs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(refs),
        "module_counts": dict(sorted(Counter(str(ref.get("module_code") or "unknown") for ref in refs).items())),
        "table_counts": dict(sorted(Counter(str(ref.get("table_name") or "unknown") for ref in refs).items())),
        "record_id_samples": [ref.get("record_id") for ref in refs[:6] if ref.get("record_id")],
    }


def compact_regression(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": profile["sku_code"],
        "display_name_cn": profile["display_name_cn"],
        "current_status": profile["current"]["status"],
        "current_core_anchors": profile["current"]["core_anchors"],
        "audit_established_anchors": profile["audit_summary"]["established_anchors"],
        "expected_invariant": "核心理由有无不变；已有核心不得因普通压力被删除。",
        "input_fingerprint_basis": [anchor["source_ref_summary"]["record_id_samples"] for anchor in profile["anchors"][:3]],
    }


def current_core_unaffected(profile: Mapping[str, Any]) -> bool:
    current_core = set(profile["current"]["core_anchors"])
    if not current_core:
        return not profile["audit_summary"]["established_anchors"]
    anchors = {
        anchor["anchor_code"]: anchor
        for anchor in profile["anchors"]
        if anchor["anchor_code"] in current_core
    }
    if set(anchors) != current_core:
        return False
    return all(anchor["audit"]["established"] for anchor in anchors.values())


def current_published_version(db: Any, category: str) -> Any:
    return db.execute(text(
        "SELECT purchase_reason_version_id, source_batch_ids_json FROM core3_purchase_reason_profile_version "
        "WHERE project_id=:project_id AND category_code=:category AND product_category=:category "
        "AND release_status='published' AND is_current IS TRUE ORDER BY published_at DESC LIMIT 1"
    ), {"project_id": PROJECT_ID, "category": category}).first()


def current_profiles(db: Any, category: str, version_id: str) -> list[Any]:
    return list(db.execute(text(
        "SELECT sku_code FROM core3_sku_purchase_reason_profile WHERE project_id=:project_id "
        "AND category_code=:category AND product_category=:category "
        "AND purchase_reason_version_id=:version_id AND is_current IS TRUE ORDER BY sku_code"
    ), {"project_id": PROJECT_ID, "category": category, "version_id": version_id}))


def capture_guard(db: Any) -> dict[str, dict[str, Any]]:
    result = {}
    for table in DOWNSTREAM_TABLES:
        row = db.execute(text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table}")).one()
        result[table] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, payload: Mapping[str, Any]) -> None:
    fields = ["category", "sku_code", "display_name_cn", "current_status", "current_core_anchors", "established_anchors", "proposition_only_anchors", "pressure_labels", "comment_wrong_dimension", "objective_block"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for category, data in payload["categories"].items():
            for profile in data["profiles"]:
                summary = profile["audit_summary"]
                writer.writerow({
                    "category": category,
                    "sku_code": profile["sku_code"],
                    "display_name_cn": profile["display_name_cn"],
                    "current_status": profile["current"]["status"],
                    "current_core_anchors": "|".join(profile["current"]["core_anchors"]),
                    "established_anchors": "|".join(summary["established_anchors"]),
                    "proposition_only_anchors": "|".join(summary["proposition_only_anchors"]),
                    "pressure_labels": "|".join(summary["pressure_labels"]),
                    "comment_wrong_dimension": summary["comment_wrong_dimension"],
                    "objective_block": summary["objective_block"],
                })


def render_markdown(payload: Mapping[str, Any], fixture: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-RP-G01 TV/AC 成立度与阻力基线",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 性质：只读审计，不是生产规则发布。",
        "- 核心口径：购买理由成立只看同锚点正向证据；普通负面和 M12C 负向作为并行压力。",
        "",
    ]
    for category, data in payload["categories"].items():
        counts = data["counts"]
        lines.extend([
            f"## {category}", "",
            f"- SKU：`{counts['sku_count']}`；当前无核心：`{counts['current_no_core']}`。",
            f"- 分层可成立且无普通压力：`{counts['guarded_reason_established']}`；成立并有普通压力：`{counts['ordinary_pressure']}`。",
            f"- 仅产品价值主张：`{counts['proposition_only']}`；评论错维度：`{counts['comment_wrong_dimension']}`。",
            f"- 负面占主导：`{counts['negative_dominant']}`；M12C 负向：`{counts['m12c_negative']}`；事实证伪阻断：`{counts['objective_block']}`。",
            f"- 未影响回归样本：`{len(data['unaffected_regression_samples'])}`。",
            "",
        ])
        if category == "TV":
            lines.extend(["### 已知基准复核", "", "| 集合 | 已知基准 | 本次观察 | 一致 |", "| --- | ---: | ---: | --- |"])
            for key, item in data["reference_check"].items():
                lines.append(f"| `{key}` | {item['expected']} | {item['observed']} | {'是' if item['matches'] else '否，需在 G04 前解释'} |")
            lines.append("")
        lines.extend(["### 验收样本", "", "| 类型 | 观察数量 | 样本数量 |", "| --- | ---: | ---: |"])
        for name, item in fixture["categories"][category].items():
            lines.append(f"| `{name}` | {item['observed_count']} | {len(item['samples'])} |")
        lines.append("")
    lines.extend([
        "## 只读证明", "",
        f"- 三张 M12D 表前后快照一致：`{payload['downstream_guard']['unchanged']}`。",
        f"- G01 验收：`{'通过' if payload['acceptance']['passed'] else '未通过'}`。",
        "- TV 已知数量只用于发现口径漂移，不作为配额，也不允许用白名单凑数。",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-fixture", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
