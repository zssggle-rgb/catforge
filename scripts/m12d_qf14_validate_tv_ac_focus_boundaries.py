#!/usr/bin/env python3
"""Validate QF12 TV/AC focus and boundary profiles without database writes."""

from __future__ import annotations

import argparse
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
    PRICE_VALUE_REASON_CODES,
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
FIXED_FOCUS_SKUS = {
    "TV": {
        "TV00029112": "海信 65E7Q",
        "TV00029936": "创维 65A7H PRO",
        "TV00027801": "TCL 65Q9L PRO",
        "TV00028829": "创维 65A6F ULTRA",
        "TV00029020": "小米 L65MC-SP",
    },
    "AC": {
        "AC00038063": "既有重点样本",
        "AC00028640": "既有重点样本",
        "AC00029751": "既有重点样本",
        "AC00036139": "既有重点样本",
        "AC00038662": "既有重点样本",
        "AC00028642": "既有重点样本",
        "AC00036739": "既有重点样本",
        "AC00036333": "既有重点样本",
        "AC00035996": "评论负向重点样本",
        "AC00036020": "评论负向重点样本",
        "AC00038680": "既有重点样本",
        "AC00034731": "既有重点样本",
        "AC00039165": "M12C 缺失重点样本",
        "AC00038066": "M12C 缺失重点样本",
        "AC00034959": "M12C 缺失重点样本",
    },
}
EXPECTED_DISTRIBUTIONS = {
    "TV": {
        "status_counts": {"ready": 238, "ready_limited": 94, "weak_expression_only": 45},
        "core_missing_count": 139,
    },
    "AC": {
        "status_counts": {"ready": 130, "ready_limited": 23, "weak_expression_only": 2},
        "core_missing_count": 25,
    },
}
DOWNSTREAM_TABLES = (
    "core3_sku_purchase_reason_profile",
    "core3_sku_purchase_reason_anchor",
    "core3_purchase_reason_profile_version",
)
HP_RANK = {
    "hp_1_or_below": Decimal("1.0"),
    "hp_1_5": Decimal("1.5"),
    "hp_2": Decimal("2.0"),
    "hp_3": Decimal("3.0"),
    "hp_3_plus": Decimal("4.0"),
}


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        guard_before = capture_guard(db)
        categories = {category: validate_category(db, category) for category in ("TV", "AC")}
        guard_after = capture_guard(db)
    if guard_before != guard_after:
        raise RuntimeError("QF14 shadow changed persisted M12D tables")

    payload = {
        "task_id": "M12D-QF-14",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": {
            "impact_set": "TV/AC 当前发布版本全部 SKU 只读重算；重点和边界 SKU 输出逐项明细。",
            "allowed_migrations": [
                "QF11 core_payment -> QF12 supporting：仅允许 core_limit 或 family_dedup",
                "当前发布画像 -> QF12 影子画像：仅记录，不写库、不发布",
            ],
            "unaffected_regression": "每个品类固定记录 20 个非重点 SKU，业务结果只读且持久化表不变。",
        },
        "categories": categories,
        "downstream_guard": {
            "before": guard_before,
            "after": guard_after,
            "unchanged": guard_before == guard_after,
        },
    }
    payload["acceptance"] = build_acceptance(payload)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    if not payload["acceptance"]["passed"]:
        raise RuntimeError(
            "QF14 acceptance failed: "
            + ", ".join(payload["acceptance"]["failed_checks"])
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "categories": {
                    category: {
                        "sku_count": result["sku_count"],
                        "status_counts": result["shadow_distribution"]["status_counts"],
                        "core_missing_count": result["shadow_distribution"]["core_missing_count"],
                        "focus_count": len(result["focus_profiles"]),
                        "price_guard_violations": len(result["price_value_guard"]["violations"]),
                    }
                    for category, result in categories.items()
                },
                "downstream_unchanged": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


def validate_category(db, category: str) -> dict[str, Any]:
    version = current_published_version(db, category)
    if version is None:
        raise RuntimeError(f"{category} has no current published M12D version")
    persisted_profiles = current_profiles(db, category, version.purchase_reason_version_id)
    persisted_anchors = current_anchors(db, category, version.purchase_reason_version_id)
    persisted_anchor_map: dict[str, dict[str, Any]] = defaultdict(dict)
    for anchor in persisted_anchors:
        persisted_anchor_map[str(anchor.sku_code)][str(anchor.anchor_code)] = {
            "role": str(anchor.role),
            "evidence_strength": str(anchor.evidence_strength),
            "confidence": str(anchor.confidence),
        }

    source_batch_ids = tuple(str(item) for item in (version.source_batch_ids_json or ()) if str(item))
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CATEGORY_TAXONOMY[category],
        product_category=category,
    )
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    )
    generator = AnchorCandidateGenerator(taxonomy)
    evidence_scorer = EvidenceStrengthScorer()
    role_classifier = ReasonRoleClassifier()
    profile_scorer = ProfileConfidenceScorer()

    profiles: dict[str, dict[str, Any]] = {}
    status_counts: Counter[str] = Counter()
    price_guard_violations: list[dict[str, Any]] = []
    price_guard_observations: list[dict[str, Any]] = []
    pre_to_final_roles: Counter[str] = Counter()

    for persisted in persisted_profiles:
        sku_code = str(persisted.sku_code)
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
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
        final_by_code = {anchor.anchor_code: anchor for anchor in final.scored_anchors}
        candidate_by_code = {
            candidate.anchor_code: candidate for candidate in candidate_set.purchase_reason_candidates
        }
        for pre in pre_anchors:
            post = final_by_code[pre.anchor_code]
            pre_to_final_roles[f"{pre.role}->{post.role}"] += 1
        market = dict(context.market_profile.summary)
        param = dict(context.param_profile.summary)
        identity = {
            "sku_code": sku_code,
            "brand_name": context.brand_name,
            "model_name": context.model_name,
            "display_name_cn": context.display_name_cn,
        }
        anchor_rows = [
            anchor_payload(
                anchor,
                pre_role=next(item.role for item in pre_anchors if item.anchor_code == anchor.anchor_code),
                persisted=persisted_anchor_map.get(sku_code, {}).get(anchor.anchor_code),
            )
            for anchor in final.scored_anchors
        ]
        profile = {
            **identity,
            "market": {
                "price_wavg": market.get("price_wavg"),
                "price_latest": market.get("price_latest"),
                "sales_volume_total": market.get("sales_volume_total"),
                "screen_size_inch": market.get("screen_size_inch"),
                "size_segment": market.get("size_segment"),
                "screen_size_class": market.get("screen_size_class"),
                "price_band_category": market.get("price_band_category"),
                "price_band_size": market.get("price_band_size"),
            },
            "param_values_json": param.get("param_values_json") or {},
            "persisted": {
                "status": str(persisted.status),
                "profile_confidence": str(persisted.profile_confidence),
                "core_payment_anchors": list(persisted.core_payment_anchors_json or ()),
                "supporting_anchors": list(persisted.supporting_anchors_json or ()),
                "weak_expression_anchors": list(persisted.weak_expression_anchors_json or ()),
                "risk_drag_anchors": list(persisted.risk_drag_anchors_json or ()),
            },
            "shadow": {
                "status": str(final.status),
                "profile_confidence": str(final.profile_confidence),
                "core_payment_anchors": list(final.core_payment_anchors_json),
                "supporting_anchors": list(final.supporting_anchors_json),
                "weak_expression_anchors": list(final.weak_expression_anchors_json),
                "risk_drag_anchors": list(final.risk_drag_anchors_json),
                "review_required": bool(final.review_required),
                "review_reason_json": final.review_reason_json,
                "confidence_basis_json": final.confidence_basis_json,
            },
            "status_change_reason_cn": status_change_reason(persisted, final),
            "anchors": anchor_rows,
        }
        profiles[sku_code] = profile
        status_counts[str(final.status)] += 1

        for code in PRICE_VALUE_REASON_CODES[category]:
            candidate = candidate_by_code.get(code)
            anchor = final_by_code.get(code)
            if candidate is None or anchor is None:
                continue
            observation = {
                "sku_code": sku_code,
                "anchor_code": code,
                "role": str(anchor.role),
                "candidate_role_cap": str(candidate.role_cap) if candidate.role_cap else None,
                "candidate_role_cap_reasons": list(candidate.role_cap_reasons),
                "downgrade_reason_code": anchor.downgrade_reason_code,
                "risk_flags": [str(flag) for flag in anchor.risk_flags_json],
            }
            weak_expression_gate = (
                str(candidate.role_cap or "") == "weak_expression"
                or anchor.downgrade_reason_code == "price_value_core_evidence_missing"
                or "price_value_core_evidence_missing" in anchor.risk_flags_json
            )
            observation["weak_expression_gate"] = weak_expression_gate
            if weak_expression_gate:
                price_guard_observations.append(observation)
            if weak_expression_gate and str(anchor.role) == "core_payment":
                price_guard_violations.append(observation)

    focus_reasons = select_focus_skus(category, profiles)
    focus_profiles = [
        {"selection_reasons_cn": reasons, **profiles[sku_code]}
        for sku_code, reasons in sorted(focus_reasons.items())
        if sku_code in profiles
    ]
    missing_fixed = sorted(set(FIXED_FOCUS_SKUS[category]) - set(profiles))
    no_core = [profile for profile in profiles.values() if not profile["shadow"]["core_payment_anchors"]]
    weak = [
        profile
        for profile in profiles.values()
        if profile["shadow"]["status"] == "weak_expression_only"
    ]
    no_core_diagnosis = diagnose_profiles(no_core)
    weak_diagnosis = diagnose_profiles(weak)
    unaffected = [
        compact_profile(profile)
        for sku_code, profile in sorted(profiles.items())
        if sku_code not in focus_reasons
    ][:20]
    persisted_status_counts = Counter(
        str(profile["persisted"]["status"]) for profile in profiles.values()
    )
    persisted_core_missing = sum(
        not profile["persisted"]["core_payment_anchors"] for profile in profiles.values()
    )
    return {
        "category": category,
        "taxonomy_version": CATEGORY_TAXONOMY[category],
        "purchase_reason_version_id": version.purchase_reason_version_id,
        "source_batch_ids": list(source_batch_ids),
        "read_scope": read_scope,
        "sku_count": len(profiles),
        "persisted_distribution": {
            "status_counts": dict(sorted(persisted_status_counts.items())),
            "core_missing_count": persisted_core_missing,
        },
        "shadow_distribution": {
            "status_counts": dict(sorted(status_counts.items())),
            "core_missing_count": len(no_core),
            "pre_to_final_role_counts": dict(sorted(pre_to_final_roles.items())),
        },
        "focus_selection": {
            "selected_count": len(focus_profiles),
            "missing_fixed_skus": missing_fixed,
            "selection_reasons_by_sku": focus_reasons,
        },
        "focus_profiles": focus_profiles,
        "price_value_guard": {
            "price_reason_codes": sorted(PRICE_VALUE_REASON_CODES[category]),
            "weak_cap_observation_count": len(price_guard_observations),
            "weak_cap_observations": price_guard_observations,
            "violations": price_guard_violations,
        },
        "no_core_diagnosis": no_core_diagnosis,
        "weak_profile_diagnosis": weak_diagnosis,
        "unaffected_regression_samples": unaffected,
    }


def select_focus_skus(
    category: str,
    profiles: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    reasons: dict[str, list[str]] = defaultdict(list)
    for sku_code, label in FIXED_FOCUS_SKUS[category].items():
        if sku_code in profiles:
            reasons[sku_code].append(label)
    if category == "TV":
        for brand_term, label in (("华为", "华为品牌重点样本"), ("huawei", "华为品牌重点样本")):
            candidates = [
                profile for profile in profiles.values() if brand_term in identity_text(profile).lower()
            ]
            if candidates:
                selected = max(candidates, key=sales_sort_value)
                reasons[str(selected["sku_code"])].append(label)
                break
        add_numeric_boundary(reasons, profiles.values(), "market.price_wavg", "最低均价边界", min)
        add_numeric_boundary(reasons, profiles.values(), "market.price_wavg", "最高均价边界", max)
        add_numeric_boundary(
            reasons,
            profiles.values(),
            "market.screen_size_inch",
            "最小尺寸边界",
            min,
        )
        add_numeric_boundary(
            reasons,
            profiles.values(),
            "market.screen_size_inch",
            "最大尺寸边界",
            max,
        )
    else:
        add_numeric_boundary(reasons, profiles.values(), "market.price_wavg", "最低均价边界", min)
        add_numeric_boundary(reasons, profiles.values(), "market.price_wavg", "最高均价边界", max)
        for installation in ("wall", "floor"):
            group = [
                profile
                for profile in profiles.values()
                if str(profile["market"].get("size_segment") or "").startswith(f"{installation}_")
            ]
            if not group:
                continue
            low = min(group, key=ac_capacity_sort_value)
            high = max(group, key=ac_capacity_sort_value)
            reasons[str(low["sku_code"])].append(f"{installation} 最小匹数边界")
            reasons[str(high["sku_code"])].append(f"{installation} 最大匹数边界")
    return {sku: list(dict.fromkeys(labels)) for sku, labels in reasons.items()}


def add_numeric_boundary(
    reasons: dict[str, list[str]],
    profiles: Iterable[Mapping[str, Any]],
    field_path: str,
    label: str,
    selector: Any,
) -> None:
    candidates = [profile for profile in profiles if decimal_at(profile, field_path) is not None]
    if not candidates:
        return
    chosen = selector(candidates, key=lambda item: decimal_at(item, field_path))
    reasons[str(chosen["sku_code"])].append(label)


def diagnose_profiles(profiles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    downgrade_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    review_bucket_counts: Counter[str] = Counter()
    for profile in profiles:
        reasons = diagnosis_reasons(profile)
        reason_counts.update(reasons)
        review_bucket_counts[diagnosis_bucket(profile, reasons)] += 1
        for anchor in profile["anchors"]:
            if anchor.get("downgrade_reason_code"):
                downgrade_counts[str(anchor["downgrade_reason_code"])] += 1
            risk_counts.update(str(flag) for flag in anchor.get("risk_flags_json") or ())
    representatives = [
        {**compact_profile(profile), "diagnosis_reasons": diagnosis_reasons(profile)}
        for profile in sorted(profiles, key=lambda item: str(item["sku_code"]))[:20]
    ]
    return {
        "sku_count": len(profiles),
        "reason_counts": dict(sorted(reason_counts.items())),
        "review_bucket_counts": dict(sorted(review_bucket_counts.items())),
        "downgrade_reason_counts": dict(sorted(downgrade_counts.items())),
        "risk_flag_counts": dict(sorted(risk_counts.items())),
        "representative_profiles": representatives,
    }


def diagnosis_reasons(profile: Mapping[str, Any]) -> list[str]:
    anchors = profile["anchors"]
    if not anchors:
        return ["no_candidate_anchor"]
    reasons: list[str] = []
    if all(anchor["evidence_strength"] in {"weak", "insufficient"} for anchor in anchors):
        reasons.append("all_anchor_evidence_weak_or_insufficient")
    if any(anchor.get("role_reason_json", {}).get("role_cap") == "weak_expression" for anchor in anchors):
        reasons.append("weak_expression_role_cap_present")
    if any(
        anchor["evidence_strength"] == "strong"
        and anchor["final_role"] == "supporting"
        and not anchor.get("downgrade_reason_code")
        for anchor in anchors
    ):
        reasons.append("strong_anchor_without_scene_fit")
    if any(anchor.get("downgrade_reason_code") == "price_value_core_evidence_missing" for anchor in anchors):
        reasons.append("price_value_core_evidence_missing")
    if any("ac_market_acceptance" in str(flag) for anchor in anchors for flag in anchor["risk_flags_json"]):
        reasons.append("ac_market_acceptance_weak_or_missing")
    if any("ac_claim_value_risk_role_dominant" in anchor["risk_flags_json"] for anchor in anchors):
        reasons.append("ac_claim_value_risk_role_dominant")
    if any(anchor["final_role"] == "risk_drag" for anchor in anchors):
        reasons.append("risk_drag_present")
    if not reasons:
        reasons.append("supporting_evidence_below_core_gate")
    return reasons


def diagnosis_bucket(profile: Mapping[str, Any], reasons: Sequence[str]) -> str:
    if "strong_anchor_without_scene_fit" in reasons:
        return "requires_scene_gate_review"
    if profile["shadow"]["review_required"]:
        return "explicit_review_required"
    if set(reasons) <= {
        "all_anchor_evidence_weak_or_insufficient",
        "weak_expression_role_cap_present",
        "price_value_core_evidence_missing",
        "ac_market_acceptance_weak_or_missing",
        "ac_claim_value_risk_role_dominant",
        "risk_drag_present",
        "supporting_evidence_below_core_gate",
    }:
        return "evidence_or_business_gate_insufficient"
    return "requires_rule_review"


def anchor_payload(anchor: Any, *, pre_role: str, persisted: Mapping[str, Any] | None) -> dict[str, Any]:
    old_role = str(persisted.get("role")) if persisted else None
    final_role = str(anchor.role)
    return {
        "anchor_code": anchor.anchor_code,
        "anchor_cn": anchor.anchor_cn,
        "anchor_family_code": anchor.anchor_family_code,
        "persisted_role": old_role,
        "qf11_role": str(pre_role),
        "final_role": final_role,
        "role_change_reason_cn": anchor_change_reason(old_role, str(pre_role), anchor),
        "evidence_strength": str(anchor.evidence_strength),
        "confidence": str(anchor.confidence),
        "adjusted_evidence_score": str(anchor.adjusted_evidence_score),
        "evidence_domains_json": [str(value) for value in anchor.evidence_domains_json],
        "risk_flags_json": [str(value) for value in anchor.risk_flags_json],
        "downgrade_reason_code": anchor.downgrade_reason_code,
        "role_reason_json": anchor.role_reason_json,
    }


def anchor_change_reason(old_role: str | None, pre_role: str, anchor: Any) -> str:
    final_role = str(anchor.role)
    if pre_role != final_role:
        reason = anchor.role_reason_json.get("core_selection_demotion_reason")
        return f"QF12 核心理由收敛：{reason or anchor.downgrade_reason_code or '画像级排序'}。"
    if old_role == final_role:
        return "当前发布结果与 QF12 影子角色一致。"
    if anchor.downgrade_reason_code:
        return f"QF11 按锚点证据门槛判定，限制原因：{anchor.downgrade_reason_code}。"
    return "QF11 按锚点作用域重算证据强度与角色，QF12 未再改变该角色。"


def status_change_reason(persisted: Any, final: Any) -> str:
    current = str(persisted.status)
    shadow = str(final.status)
    core_count = len(final.core_payment_anchors_json)
    if current == shadow:
        return "状态不变；QF12 仍按核心理由数量和画像置信度判定。"
    if core_count:
        return (
            f"影子画像有 {core_count} 个核心成交理由，画像置信度 "
            f"{final.profile_confidence}，因此状态由 {current} 变为 {shadow}。"
        )
    limited_confidence = final.confidence_basis_json.get("limited_confidence")
    return (
        "影子画像无核心成交理由；按最高支持理由置信度 "
        f"{limited_confidence} 判定，状态由 {current} 变为 {shadow}。"
    )


def compact_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": profile["sku_code"],
        "display_name_cn": profile["display_name_cn"],
        "market": profile["market"],
        "persisted_status": profile["persisted"]["status"],
        "shadow_status": profile["shadow"]["status"],
        "shadow_confidence": profile["shadow"]["profile_confidence"],
        "core_payment_anchors": profile["shadow"]["core_payment_anchors"],
        "supporting_anchors": profile["shadow"]["supporting_anchors"],
        "weak_expression_anchors": profile["shadow"]["weak_expression_anchors"],
        "risk_drag_anchors": profile["shadow"]["risk_drag_anchors"],
    }


def build_acceptance(payload: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {"persisted_tables_unchanged": payload["downstream_guard"]["unchanged"]}
    for category, result in payload["categories"].items():
        expected = EXPECTED_DISTRIBUTIONS[category]
        checks[f"{category.lower()}_distribution_matches_qf12"] = (
            result["shadow_distribution"]["status_counts"] == expected["status_counts"]
            and result["shadow_distribution"]["core_missing_count"]
            == expected["core_missing_count"]
        )
        checks[f"{category.lower()}_price_weak_cap_never_core"] = not result[
            "price_value_guard"
        ]["violations"]
        checks[f"{category.lower()}_fixed_focus_complete"] = not result["focus_selection"][
            "missing_fixed_skus"
        ]
        checks[f"{category.lower()}_unaffected_samples_20"] = (
            len(result["unaffected_regression_samples"]) == 20
        )
    tv_profiles = {
        item["sku_code"]: item for item in payload["categories"]["TV"]["focus_profiles"]
    }
    checks["tv_65e7q_budget_value_not_core"] = (
        "TV00029112" in tv_profiles
        and "same_price_core_config_gain"
        not in tv_profiles["TV00029112"]["shadow"]["core_payment_anchors"]
    )
    checks["tv_65e7q_budget_value_gate_observed"] = any(
        item["sku_code"] == "TV00029112"
        and item["anchor_code"] == "same_price_core_config_gain"
        and item["weak_expression_gate"]
        for item in payload["categories"]["TV"]["price_value_guard"]["weak_cap_observations"]
    )
    failed = sorted(key for key, value in checks.items() if not value)
    return {"passed": not failed, "checks": checks, "failed_checks": failed}


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-14 TV/AC 重点与边界 SKU 影子验证",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 范围：只读重算 QF11 锚点角色和 QF12 画像决策；不改规则、不写 current、不改变竞品 Top 3。",
        f"- 总体验收：`{'通过' if payload['acceptance']['passed'] else '未通过'}`",
        "",
        "## 1. 双品类结果",
        "",
        "| 品类 | SKU | ready | limited | weak | 无核心 | 重点/边界样本 | 价格弱表达误升核心 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in ("TV", "AC"):
        result = payload["categories"][category]
        statuses = result["shadow_distribution"]["status_counts"]
        lines.append(
            f"| {category} | {result['sku_count']} | {statuses.get('ready', 0)} | "
            f"{statuses.get('ready_limited', 0)} | {statuses.get('weak_expression_only', 0)} | "
            f"{result['shadow_distribution']['core_missing_count']} | "
            f"{result['focus_selection']['selected_count']} | "
            f"{len(result['price_value_guard']['violations'])} |"
        )
    for section_number, category in (("2.1", "TV"), ("2.2", "AC")):
        result = payload["categories"][category]
        lines.extend(["", f"## {section_number} {category} 重点与边界 SKU", ""])
        lines.extend(
            [
                "| SKU | 产品 | 选择原因 | 当前状态 -> 影子状态 | 影子核心理由 | 影子支持理由 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in result["focus_profiles"]:
            lines.append(
                f"| {item['sku_code']} | {item['display_name_cn']} | "
                f"{'；'.join(item['selection_reasons_cn'])} | "
                f"{item['persisted']['status']} -> {item['shadow']['status']} | "
                f"{join_codes(item['shadow']['core_payment_anchors'])} | "
                f"{join_codes(item['shadow']['supporting_anchors'])} |"
            )
        diagnosis = result["no_core_diagnosis"]
        weak = result["weak_profile_diagnosis"]
        lines.extend(
            [
                "",
                f"### {category} 无核心/弱画像归因",
                "",
                f"- 无核心 SKU：`{diagnosis['sku_count']}`；归因：`{diagnosis['reason_counts']}`",
                f"- 归因复核桶：`{diagnosis['review_bucket_counts']}`",
                f"- 弱画像 SKU：`{weak['sku_count']}`；归因：`{weak['reason_counts']}`",
                f"- 价格弱表达/核心证据不足门槛观察：`{result['price_value_guard']['weak_cap_observation_count']}`；误升核心：`{len(result['price_value_guard']['violations'])}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 3. 门禁结论",
            "",
            f"- 持久化表未变化：`{payload['downstream_guard']['unchanged']}`",
            f"- 检查项：`{payload['acceptance']['checks']}`",
            "- 本报告中的 `requires_scene_gate_review` 只表示 QF15 前需复核场景门槛，不等同于数据缺失，也未在 QF14 修改规则。",
            "- QF14 未发布版本、未运行竞品智能体、未修改线上 Top 3。",
            "",
        ]
    )
    return "\n".join(lines)


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


def current_anchors(db, category: str, version_id: str) -> list[Any]:
    return list(
        db.scalars(
            select(entities.Core3SkuPurchaseReasonAnchor)
            .where(entities.Core3SkuPurchaseReasonAnchor.project_id == PROJECT_ID)
            .where(entities.Core3SkuPurchaseReasonAnchor.category_code == category)
            .where(entities.Core3SkuPurchaseReasonAnchor.product_category == category)
            .where(entities.Core3SkuPurchaseReasonAnchor.purchase_reason_version_id == version_id)
            .where(entities.Core3SkuPurchaseReasonAnchor.is_current.is_(True))
        )
    )


def capture_guard(db) -> dict[str, dict[str, Any]]:
    result = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table_name}")
        ).one()
        result[table_name] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def identity_text(profile: Mapping[str, Any]) -> str:
    return " ".join(
        str(profile.get(key) or "")
        for key in ("brand_name", "model_name", "display_name_cn")
    )


def sales_sort_value(profile: Mapping[str, Any]) -> Decimal:
    return decimal_value(profile["market"].get("sales_volume_total")) or Decimal("0")


def ac_capacity_sort_value(profile: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
    segment = str(profile["market"].get("size_segment") or "")
    hp_code = next(
        (code for code in sorted(HP_RANK, key=len, reverse=True) if segment.endswith(code)),
        "",
    )
    return HP_RANK.get(hp_code, Decimal("0")), sales_sort_value(profile)


def decimal_at(profile: Mapping[str, Any], field_path: str) -> Decimal | None:
    value: Any = profile
    for key in field_path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return decimal_value(value)


def decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def join_codes(values: Sequence[str]) -> str:
    return "、".join(values) if values else "-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
