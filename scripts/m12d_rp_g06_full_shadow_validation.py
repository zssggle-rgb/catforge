#!/usr/bin/env python3
"""Full read-only TV/AC G06 shadow and business validation."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.core3_real_data.constants import (  # noqa: E402
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DProfileStatus,
    M12DPurchasePressureLevel,
    M12DReasonEstablishmentStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_candidate_generator import (  # noqa: E402
    AnchorCandidateGenerator,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (  # noqa: E402
    M12DAnchorTaxonomyLoader,
)
from app.services.core3_real_data.purchase_reason_context_builder import (  # noqa: E402
    SkuPurchaseReasonContextBuilder,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (  # noqa: E402
    PurchaseReasonProfileScoringService,
)
from app.services.core3_real_data.purchase_reason_release_quality import (  # noqa: E402
    M12DReleaseQualityEvaluator,
)
from app.services.core3_real_data.repositories import (  # noqa: E402
    Core3RepositoryContext,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
TAXONOMY_VERSIONS = {
    "TV": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    "AC": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
}
DOWNSTREAM_TABLES = (
    "core3_sku_purchase_reason_profile",
    "core3_sku_purchase_reason_anchor",
    "core3_purchase_reason_profile_version",
)
ESTABLISHED = {
    M12DReasonEstablishmentStatus.ESTABLISHED.value,
    M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
}
BLOCKING_PRESSURES = {"objective_falsification", "evidence_misalignment"}


def main() -> int:
    args = parse_args()
    qf15a = json.loads(Path(args.qf15a_json).read_text(encoding="utf-8"))
    qf14 = json.loads(Path(args.qf14_json).read_text(encoding="utf-8"))
    g04 = json.loads(Path(args.g04_json).read_text(encoding="utf-8"))
    g04_index = build_g04_index(g04)
    qf15a_skus = {str(row["sku_code"]) for row in qf15a.get("no_core_sku_audit") or []}
    focus_skus = {
        category: [
            str(row["sku_code"])
            for row in qf14["categories"][category]["focus_profiles"]
        ]
        for category in ("TV", "AC")
    }

    engine = create_engine(args.database_url, future=True, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as db:
        before = capture_guard(db)
        categories = {
            category: validate_category(
                db,
                category=category,
                focus_skus=focus_skus[category],
                qf15a_skus=qf15a_skus if category == "TV" else set(),
                g04_index=g04_index[category],
            )
            for category in ("TV", "AC")
        }
        after = capture_guard(db)
    engine.dispose()

    failed_checks: list[str] = []
    if before != after:
        failed_checks.append("downstream_tables_changed")
    for category, result in categories.items():
        checks = result["checks"]
        failed_checks.extend(
            f"{category.lower()}_{code}"
            for code, passed in checks.items()
            if not passed
        )
    payload = {
        "task_id": "M12D-RP-G06",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": {
            "pipeline": "205 当前发布 TV/AC 全量只读重建 context、candidate、establishment、pressure、profile 和 release quality。",
            "tv_qf15a_count": len(qf15a_skus),
            "focus_counts": {
                category: len(values) for category, values in focus_skus.items()
            },
            "write_policy": "不写 M12D 表、不切 current、不运行竞品智能体。",
        },
        "categories": categories,
        "downstream_guard": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "acceptance": {"passed": not failed_checks, "failed_checks": failed_checks},
    }
    write_outputs(args, payload)
    print(
        json.dumps(
            {
                "status": "ok" if not failed_checks else "failed",
                "categories": {
                    category: {
                        "sku_count": result["summary"]["sku_count"],
                        "status_counts": result["summary"]["status_counts"],
                        "added_core_count": result["summary"]["added_core_count"],
                        "removed_core_count": result["summary"]["removed_core_count"],
                        "release_quality_status": result["release_quality"][
                            "release_quality_status"
                        ],
                        "failed_checks": [
                            code
                            for code, passed in result["checks"].items()
                            if not passed
                        ],
                    }
                    for category, result in categories.items()
                },
                "downstream_unchanged": before == after,
                "failed_checks": failed_checks,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failed_checks else 1


def validate_category(
    db: Any,
    *,
    category: str,
    focus_skus: list[str],
    qf15a_skus: set[str],
    g04_index: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    version = current_version(db, category)
    persisted = current_profiles(db, category, str(version.purchase_reason_version_id))
    source_batches = [
        str(value) for value in (version.source_batch_ids_json or []) if str(value)
    ]
    read_scope = f"serving-scope:{category}:{','.join(source_batches)}"
    taxonomy = M12DAnchorTaxonomyLoader().load(
        TAXONOMY_VERSIONS[category], product_category=category
    )
    builder = SkuPurchaseReasonContextBuilder(
        Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    )
    generator = AnchorCandidateGenerator(taxonomy)
    scorer = PurchaseReasonProfileScoringService()

    status_counts: Counter[str] = Counter()
    consumption_counts: Counter[str] = Counter()
    establishment_counts: Counter[str] = Counter()
    pressure_counts: Counter[str] = Counter()
    selected_core_pressure_counts: Counter[str] = Counter()
    added_core: list[dict[str, Any]] = []
    removed_core: list[dict[str, Any]] = []
    invalid_new_core: list[dict[str, Any]] = []
    pressure_source_failures: list[dict[str, Any]] = []
    pressure_role_violations: list[dict[str, str]] = []
    proposition_core: list[dict[str, str]] = []
    g04_drift: list[dict[str, str]] = []
    profile_rows: list[dict[str, Any]] = []
    release_profile_rows: list[dict[str, Any]] = []
    profiles_by_sku: dict[str, dict[str, Any]] = {}

    for index, (sku_code, persisted_row) in enumerate(
        sorted(persisted.items()), start=1
    ):
        context = builder.build_context(
            batch_id=read_scope,
            sku_code=sku_code,
            product_category=category,
            detail_limit=50,
        )
        candidate_set = generator.generate(context)
        result = scorer.score(candidate_set=candidate_set, context=context)
        status = str(result.status)
        status_counts[status] += 1
        mode = consumption_mode(result)
        consumption_counts[mode] += 1
        old_core = list(persisted_row["core_payment_anchors"])
        new_core = list(result.core_payment_anchors_json)
        result_by_code = {
            anchor.anchor_code: anchor for anchor in result.scored_anchors
        }

        for anchor in result.scored_anchors:
            establishment_counts[str(anchor.establishment_status)] += 1
            pressure_level = str(anchor.pressure_level)
            if anchor.anchor_code in new_core:
                selected_core_pressure_counts[pressure_level] += 1
            if (
                anchor.core_eligible is True
                and pressure_level != M12DPurchasePressureLevel.NONE.value
                and str(anchor.role)
                in {
                    M12DAnchorRole.WEAK_EXPRESSION.value,
                    M12DAnchorRole.RISK_DRAG.value,
                }
            ):
                pressure_role_violations.append(
                    {
                        "sku_code": sku_code,
                        "anchor_code": anchor.anchor_code,
                        "pressure_level": pressure_level,
                        "role": str(anchor.role),
                    }
                )
            for tag in anchor.pressure_tags_json:
                pressure_counts[str(tag.pressure_type)] += 1
                if (
                    str(tag.affected_anchor_code) != anchor.anchor_code
                    or not tag.source_refs
                ):
                    pressure_source_failures.append(
                        {
                            "sku_code": sku_code,
                            "anchor_code": anchor.anchor_code,
                            "pressure_type": str(tag.pressure_type),
                        }
                    )
            if (
                str(anchor.establishment_status)
                == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
                and anchor.anchor_code in new_core
            ):
                proposition_core.append(
                    {"sku_code": sku_code, "anchor_code": anchor.anchor_code}
                )
            previous = g04_index.get(sku_code, {}).get(anchor.anchor_code)
            if previous is None:
                g04_drift.append(
                    {
                        "sku_code": sku_code,
                        "anchor_code": anchor.anchor_code,
                        "field": "missing",
                    }
                )
            else:
                compare_g04(previous, anchor, g04_drift)

        for anchor_code in sorted(set(new_core) - set(old_core)):
            anchor = result_by_code[anchor_code]
            audit = audit_new_core(sku_code, anchor)
            added_core.append(audit)
            if not audit["passed"]:
                invalid_new_core.append(audit)
        for anchor_code in sorted(set(old_core) - set(new_core)):
            anchor = result_by_code.get(anchor_code)
            removed_core.append(
                {
                    "sku_code": sku_code,
                    "anchor_code": anchor_code,
                    "new_role": str(anchor.role) if anchor else "candidate_missing",
                    "establishment_status": (
                        str(anchor.establishment_status)
                        if anchor
                        else "candidate_missing"
                    ),
                    "reason": removal_reason(anchor),
                }
            )

        profile = {
            "sku_code": sku_code,
            "display_name_cn": context.display_name_cn,
            "category_code": category,
            "product_category": category,
            "old_status": persisted_row["status"],
            "new_status": status,
            "old_core": old_core,
            "new_core": new_core,
            "established_anchors": list(result.established_anchors_json),
            "proposition_anchors": list(result.proposition_anchors_json),
            "pressure_summary": dict(result.pressure_summary_json),
            "profile_confidence": str(result.profile_confidence),
            "consumption_mode": mode,
            "review_required": bool(result.review_required),
            "input_quality_summary": compact_input_quality(context.input_quality_json),
            "anchors": [
                focus_anchor_payload(anchor) for anchor in result.scored_anchors
            ],
        }
        release_profile_rows.append(
            {
                "sku_code": sku_code,
                "category_code": category,
                "product_category": category,
                "status": status,
                "review_required": bool(result.review_required),
                "core_payment_anchors_json": new_core,
                "input_quality_json": context.input_quality_json,
            }
        )
        profiles_by_sku[sku_code] = profile
        profile_rows.append(profile)
        if index % 25 == 0 or index == len(persisted):
            print(f"{category}: {index}/{len(persisted)}", flush=True)

    focus_results = [
        focus_validation(profiles_by_sku.get(sku_code), sku_code)
        for sku_code in focus_skus
    ]
    quality = M12DReleaseQualityEvaluator().evaluate(
        category_code=category,
        product_category=category,
        profiles=release_profile_rows,
        expected_sku_count=len(persisted),
        focus_validation_results=focus_results,
    )
    qf15a_rows = [
        qf15a_payload(profiles_by_sku[sku_code])
        for sku_code in sorted(qf15a_skus)
        if sku_code in profiles_by_sku
    ]
    g04_invariant_skus = [
        profile
        for profile in profile_rows
        if not any(item["sku_code"] == profile["sku_code"] for item in g04_drift)
    ][:20]
    summary = {
        "sku_count": len(profile_rows),
        "anchor_count": sum(len(row["anchors"]) for row in profile_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "consumption_mode_counts": dict(sorted(consumption_counts.items())),
        "establishment_status_counts": dict(sorted(establishment_counts.items())),
        "pressure_type_counts": dict(sorted(pressure_counts.items())),
        "selected_core_pressure_level_counts": dict(
            sorted(selected_core_pressure_counts.items())
        ),
        "added_core_count": len(added_core),
        "added_core_sku_count": len({row["sku_code"] for row in added_core}),
        "removed_core_count": len(removed_core),
        "removed_core_sku_count": len({row["sku_code"] for row in removed_core}),
        "invalid_new_core_count": len(invalid_new_core),
        "pressure_source_failure_count": len(pressure_source_failures),
        "pressure_role_violation_count": len(pressure_role_violations),
        "proposition_core_count": len(proposition_core),
        "g04_drift_count": len(g04_drift),
        "g04_invariant_regression_sku_count": len(g04_invariant_skus),
    }
    qf15a_summary = {
        "expected_count": len(qf15a_skus),
        "evaluated_count": len(qf15a_rows),
        "with_core_count": sum(bool(row["new_core"]) for row in qf15a_rows),
        "without_core_count": sum(not row["new_core"] for row in qf15a_rows),
        "status_counts": dict(Counter(row["new_status"] for row in qf15a_rows)),
    }
    category_boundary_checks = category_specific_checks(category, profiles_by_sku)
    release_quality = quality.model_dump(mode="json")
    checks = {
        "full_scope_complete": len(profile_rows) == len(persisted)
        and bool(profile_rows),
        "new_core_business_audit": not invalid_new_core,
        "pressure_sources_traceable": not pressure_source_failures,
        "pressure_does_not_delete_established_reason": not pressure_role_violations,
        "proposition_never_core": not proposition_core,
        "g04_deterministic": not g04_drift,
        "unaffected_regression_20": len(g04_invariant_skus) >= 20,
        "focus_complete_and_passed": len(focus_results) == len(focus_skus)
        and all(row["passed"] for row in focus_results),
        "qf15a_139_complete": category != "TV"
        or (len(qf15a_skus) == 139 and len(qf15a_rows) == 139),
        "qf15a_expected_distribution": category != "TV"
        or (
            qf15a_summary["with_core_count"] == 107
            and qf15a_summary["without_core_count"] == 32
        ),
        **category_boundary_checks,
        "release_not_blocked": release_quality["release_quality_status"] != "blocked",
    }
    return {
        "category": category,
        "taxonomy_version": TAXONOMY_VERSIONS[category],
        "purchase_reason_version_id": str(version.purchase_reason_version_id),
        "read_scope": read_scope,
        "summary": summary,
        "release_quality": release_quality,
        "focus_results": focus_results,
        "focus_profiles": [
            profiles_by_sku[sku] for sku in focus_skus if sku in profiles_by_sku
        ],
        "qf15a_summary": qf15a_summary if category == "TV" else None,
        "qf15a_profiles": qf15a_rows if category == "TV" else [],
        "added_core_audit": added_core,
        "removed_core_audit": removed_core,
        "invalid_samples": {
            "new_core": invalid_new_core[:20],
            "pressure_source": pressure_source_failures[:20],
            "pressure_role": pressure_role_violations[:20],
            "proposition_core": proposition_core[:20],
            "g04_drift": g04_drift[:20],
        },
        "unaffected_regression_skus": [
            {
                "sku_code": row["sku_code"],
                "display_name_cn": row["display_name_cn"],
                "new_status": row["new_status"],
                "new_core": row["new_core"],
            }
            for row in g04_invariant_skus
        ],
        "checks": checks,
    }


def audit_new_core(sku_code: str, anchor: Any) -> dict[str, Any]:
    domains = {str(value) for value in anchor.establishment_domains_json}
    comment_required = M12DEvidenceDomain.COMMENT_PERCEPTION.value in domains
    comment_traced = any(
        str(ref.module_code) == "M05C" for ref in anchor.user_support_evidence_json
    )
    checks = {
        "established": str(anchor.establishment_status) in ESTABLISHED,
        "score_at_least_7": Decimal(str(anchor.establishment_score or 0))
        >= Decimal("7"),
        "core_eligible": anchor.core_eligible is True,
        "business_boundary_passed": bool(
            anchor.role_reason_json.get("business_boundary_passed")
        ),
        "proposition_evidence_traced": bool(anchor.proposition_evidence_json),
        "user_or_market_support_traced": bool(anchor.user_support_evidence_json),
        "comment_trace_when_used": not comment_required or comment_traced,
        "not_proposition": str(anchor.establishment_status)
        != M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value,
    }
    return {
        "sku_code": sku_code,
        "anchor_code": anchor.anchor_code,
        "anchor_cn": anchor.anchor_cn,
        "establishment_status": str(anchor.establishment_status),
        "establishment_score": str(anchor.establishment_score),
        "user_validation_status": str(anchor.user_validation_status),
        "pressure_level": str(anchor.pressure_level),
        "establishment_domains": sorted(domains),
        "proposition_evidence_count": len(anchor.proposition_evidence_json),
        "user_support_evidence_count": len(anchor.user_support_evidence_json),
        "evidence_ids_sample": evidence_ids_sample(anchor.source_refs_json),
        "checks": checks,
        "passed": all(checks.values()),
    }


def removal_reason(anchor: Any | None) -> str:
    if anchor is None:
        return "candidate_missing"
    if (
        str(anchor.establishment_status)
        == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
    ):
        return "proposition_only"
    if str(anchor.establishment_status) == M12DReasonEstablishmentStatus.REJECTED.value:
        return "rejected"
    if anchor.role == M12DAnchorRole.SUPPORTING.value:
        return str(
            anchor.role_reason_json.get("core_selection_demotion_reason")
            or "established_supporting_not_core_eligible"
        )
    return str(anchor.downgrade_reason_code or "not_selected")


def compare_g04(
    previous: Mapping[str, Any], anchor: Any, failures: list[dict[str, str]]
) -> None:
    current = {
        "establishment_status": str(anchor.establishment_status),
        "establishment_score": str(anchor.establishment_score),
        "user_validation_status": str(anchor.user_validation_status),
        "core_eligible": bool(anchor.core_eligible),
        "pressure_level": str(anchor.pressure_level),
    }
    for field, value in current.items():
        previous_value = previous.get(field)
        if field == "establishment_score":
            same = Decimal(str(previous_value)) == Decimal(str(value))
        else:
            same = previous_value == value
        if not same:
            failures.append(
                {
                    "sku_code": anchor.sku_code,
                    "anchor_code": anchor.anchor_code,
                    "field": field,
                }
            )


def focus_validation(profile: dict[str, Any] | None, sku_code: str) -> dict[str, Any]:
    if profile is None:
        return {
            "sku_code": sku_code,
            "passed": False,
            "reason_cn": "重点 SKU 未生成画像。",
        }
    invalid_core = [
        anchor
        for anchor in profile["anchors"]
        if anchor["role"] == M12DAnchorRole.CORE_PAYMENT.value
        and (
            anchor["establishment_status"] not in ESTABLISHED
            or Decimal(anchor["establishment_score"]) < Decimal("7")
            or not anchor["core_eligible"]
        )
    ]
    passed = not invalid_core and profile["new_status"] not in {
        M12DProfileStatus.MISSING_INPUT.value,
        M12DProfileStatus.FAILED.value,
    }
    return {
        "sku_code": sku_code,
        "passed": passed,
        "reason_cn": "重点 SKU 角色、门槛和消费状态通过。"
        if passed
        else "重点 SKU 存在无效核心或画像不可用。",
    }


def category_specific_checks(
    category: str, profiles_by_sku: Mapping[str, dict[str, Any]]
) -> dict[str, bool]:
    if category != "TV":
        return {}
    profile = profiles_by_sku.get("TV00029112")
    if profile is None:
        return {"tv_65e7q_proposition_boundary": False}
    core_anchors = set(profile["new_core"])
    return {
        "tv_65e7q_proposition_boundary": not core_anchors.intersection(
            {"same_price_core_config_gain", "big_screen_cinema_substitution"}
        )
    }


def qf15a_payload(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": profile["sku_code"],
        "display_name_cn": profile["display_name_cn"],
        "old_status": profile["old_status"],
        "new_status": profile["new_status"],
        "old_core": profile["old_core"],
        "new_core": profile["new_core"],
        "proposition_anchors": profile["proposition_anchors"],
        "consumption_mode": profile["consumption_mode"],
    }


def focus_anchor_payload(anchor: Any) -> dict[str, Any]:
    return {
        "anchor_code": anchor.anchor_code,
        "anchor_cn": anchor.anchor_cn,
        "role": str(anchor.role),
        "establishment_status": str(anchor.establishment_status),
        "establishment_score": str(anchor.establishment_score),
        "user_validation_status": str(anchor.user_validation_status),
        "core_eligible": anchor.core_eligible,
        "pressure_level": str(anchor.pressure_level),
        "pressure_summary_cn": anchor.pressure_summary_cn,
        "comparison_limitations": [
            compact_comparison_limitation(item)
            for item in anchor.comparison_limitations_json
        ],
        "support_summary_cn": anchor.support_summary_cn,
        "source_refs": compact_source_refs(anchor.source_refs_json),
    }


def compact_comparison_limitation(limitation: Any) -> dict[str, Any]:
    return {
        "limitation_code": str(limitation.limitation_code),
        "scope": str(limitation.scope),
        "limits_comparison": bool(limitation.limits_comparison),
        "summary_cn": str(limitation.summary_cn),
        "source_ref_count": len(limitation.source_refs),
    }


def compact_source_refs(source_refs: list[Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for source_ref in source_refs:
        key = (str(source_ref.module_code), str(source_ref.table_name))
        group = groups.setdefault(
            key,
            {
                "module_code": key[0],
                "table_name": key[1],
                "source_ref_count": 0,
                "evidence_count": 0,
                "record_ids_sample": [],
                "evidence_ids_sample": [],
            },
        )
        group["source_ref_count"] += 1
        evidence_ids = [str(value) for value in source_ref.evidence_ids or []]
        group["evidence_count"] += len(evidence_ids)
        _append_samples(group["record_ids_sample"], [str(source_ref.record_id)], 3)
        _append_samples(group["evidence_ids_sample"], evidence_ids, 3)
    return [groups[key] for key in sorted(groups)]


def _append_samples(target: list[str], values: list[str], limit: int) -> None:
    if len(target) >= limit:
        return
    for value in values:
        if value not in target:
            target.append(value)
        if len(target) >= limit:
            return


def compact_input_quality(input_quality: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for module_code, quality in input_quality.items():
        issues = list(quality.issues or [])
        result[str(module_code)] = {
            "availability": str(quality.availability),
            "usability": str(quality.usability),
            "issue_count": len(issues),
            "issue_codes": list(dict.fromkeys(str(issue.code) for issue in issues)),
        }
    return result


def evidence_ids_sample(source_refs: list[Any]) -> list[str]:
    evidence_ids: list[str] = []
    for source_ref in source_refs:
        evidence_ids.extend(str(value) for value in source_ref.evidence_ids or [])
        if len(evidence_ids) >= 5:
            break
    return list(dict.fromkeys(evidence_ids))[:5]


def consumption_mode(result: Any) -> str:
    if result.core_payment_anchors_json:
        return "strong"
    if result.established_anchors_json:
        return "limited"
    return "facts_only"


def build_g04_index(
    payload: dict[str, Any],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    result: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for category, category_payload in payload["categories"].items():
        by_sku: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in category_payload["anchors"]:
            by_sku[str(row["sku_code"])][str(row["anchor_code"])] = row
        result[category] = dict(by_sku)
    return result


def current_version(db: Any, category: str) -> Any:
    row = db.execute(
        text(
            "SELECT purchase_reason_version_id, source_batch_ids_json "
            "FROM core3_purchase_reason_profile_version "
            "WHERE project_id=:project_id AND category_code=:category "
            "AND product_category=:category AND release_status='published' "
            "AND is_current IS TRUE ORDER BY published_at DESC LIMIT 1"
        ),
        {"project_id": PROJECT_ID, "category": category},
    ).first()
    if row is None:
        raise RuntimeError(f"{category} current published M12D version is missing")
    return row


def current_profiles(
    db: Any, category: str, version_id: str
) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT sku_code, status, core_payment_anchors_json "
            "FROM core3_sku_purchase_reason_profile "
            "WHERE project_id=:project_id AND category_code=:category "
            "AND product_category=:category AND purchase_reason_version_id=:version_id "
            "AND is_current IS TRUE ORDER BY sku_code"
        ),
        {"project_id": PROJECT_ID, "category": category, "version_id": version_id},
    )
    return {
        str(row.sku_code): {
            "status": str(row.status),
            "core_payment_anchors": list(row.core_payment_anchors_json or []),
        }
        for row in rows
    }


def capture_guard(db: Any) -> dict[str, dict[str, Any]]:
    result = {}
    for table in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"SELECT count(*) AS n, max(updated_at) AS latest FROM {table}")
        ).one()
        result[table] = {"count": int(row.n), "latest": str(row.latest)}
    return result


def write_outputs(args: argparse.Namespace, payload: dict[str, Any]) -> None:
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
            "sku_code",
            "anchor_code",
            "change_type",
            "establishment_status",
            "establishment_score",
            "pressure_level",
            "audit_passed",
            "reason",
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for category, result in payload["categories"].items():
            for row in result["added_core_audit"]:
                writer.writerow(
                    {
                        "category": category,
                        "sku_code": row["sku_code"],
                        "anchor_code": row["anchor_code"],
                        "change_type": "added_core",
                        "establishment_status": row["establishment_status"],
                        "establishment_score": row["establishment_score"],
                        "pressure_level": row["pressure_level"],
                        "audit_passed": row["passed"],
                        "reason": "",
                    }
                )
            for row in result["removed_core_audit"]:
                writer.writerow(
                    {
                        "category": category,
                        "sku_code": row["sku_code"],
                        "anchor_code": row["anchor_code"],
                        "change_type": "removed_core",
                        "establishment_status": row["establishment_status"],
                        "establishment_score": "",
                        "pressure_level": "",
                        "audit_passed": True,
                        "reason": row["reason"],
                    }
                )
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    fixture = {
        "fixture_version": "m12d_rp_g06_validated_v0.1",
        "task_id": payload["task_id"],
        "generated_at": payload["generated_at"],
        "categories": {
            category: {
                "taxonomy_version": result["taxonomy_version"],
                "release_quality": result["release_quality"],
                "summary": result["summary"],
                "focus_profiles": result["focus_profiles"],
            }
            for category, result in payload["categories"].items()
        },
    }
    output_fixture.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M12D-RP-G06 TV/AC 全量影子与发布门槛复算",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        "- 性质：205 当前发布范围全量只读重建；未写表、未切 current、未运行竞品智能体。",
        "",
    ]
    for category, result in payload["categories"].items():
        summary = result["summary"]
        quality = result["release_quality"]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- SKU：`{summary['sku_count']}`；锚点：`{summary['anchor_count']}`。",
                f"- 状态：`{json.dumps(summary['status_counts'], ensure_ascii=False)}`；消费能力：`{json.dumps(summary['consumption_mode_counts'], ensure_ascii=False)}`。",
                f"- 新增核心：`{summary['added_core_count']}` 条 / `{summary['added_core_sku_count']}` SKU；删除核心：`{summary['removed_core_count']}` 条 / `{summary['removed_core_sku_count']}` SKU。",
                f"- 新增核心业务审计失败：`{summary['invalid_new_core_count']}`；压力来源失败：`{summary['pressure_source_failure_count']}`；压力误删成立理由：`{summary['pressure_role_violation_count']}`；proposition 误入核心：`{summary['proposition_core_count']}`。",
                f"- 与 G04 成立度/压力漂移：`{summary['g04_drift_count']}`；未影响回归：`{summary['g04_invariant_regression_sku_count']}` SKU。",
                f"- 发布质量：`{quality['release_quality_status']}`；失败门槛：`{quality['failure_reason_codes']}`。",
                f"- 重点样本：`{len(result['focus_results'])}`，通过：`{sum(row['passed'] for row in result['focus_results'])}`。",
            ]
        )
        if category == "TV":
            qf15a = result["qf15a_summary"]
            lines.extend(
                [
                    f"- QF15A 139：复核 `{qf15a['evaluated_count']}`；形成核心 `{qf15a['with_core_count']}`；仍无核心 `{qf15a['without_core_count']}`。",
                ]
            )
        lines.extend(
            [
                f"- 检查项：`{json.dumps(result['checks'], ensure_ascii=False)}`。",
                "",
            ]
        )
    lines.extend(
        [
            "## 总体验收",
            "",
            f"- 三张 M12D 表前后快照一致：`{payload['downstream_guard']['unchanged']}`。",
            f"- G06：`{'通过' if payload['acceptance']['passed'] else '未通过'}`。",
            f"- 未通过项：`{payload['acceptance']['failed_checks']}`。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--qf15a-json",
        default=str(
            REPO_ROOT
            / "docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15A_tv_no_core_threshold_audit.json"
        ),
    )
    parser.add_argument(
        "--qf14-json",
        default=str(
            REPO_ROOT
            / "docs/core3_mvp/real_data_v2/current_implementation/M12D_QF14_tv_ac_focus_boundary_shadow.json"
        ),
    )
    parser.add_argument(
        "--g04-json",
        default=str(
            REPO_ROOT
            / "docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G04_tv_ac_establishment_shadow.json"
        ),
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-fixture", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
