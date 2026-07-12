#!/usr/bin/env python3
"""Prepare, publish, and verify the M12D RP-G10 TV/AC release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.models import entities  # noqa: E402
from app.services.core3_real_data.constants import (  # noqa: E402
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_RULE_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    Core3CategoryCode,
    M12DReleaseQualityStatus,
    M12DReleaseStatus,
)
from app.services.core3_real_data.purchase_reason_profile_repositories import (  # noqa: E402
    PurchaseReasonProfileRepository,
)
from app.services.core3_real_data.purchase_reason_profile_runner import (  # noqa: E402
    PurchaseReasonProfileBatchGenerator,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext  # noqa: E402


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_FOCUS_PATH = (
    REPO_ROOT
    / "docs/core3_mvp/real_data_v2/current_implementation/"
    "M12D_RP_G06_validated_fixture.json"
)
PROFILE_VERSIONS = {
    "TV": "m12d_tv_purchase_reason_profile_v0_3",
    "AC": "m12d_ac_purchase_reason_profile_v0_3",
}
TAXONOMY_VERSIONS = {
    "TV": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    "AC": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
}
EXPECTED_STATUS_COUNTS = {
    "TV": {"ready": 335, "ready_limited": 13, "weak_expression_only": 29},
    "AC": {"ready": 143, "ready_limited": 1, "weak_expression_only": 11},
}
EXPECTED_SKU_COUNTS = {"TV": 377, "AC": 155}
PROFILE_BUSINESS_FIELDS = (
    "sku_code",
    "status",
    "profile_confidence",
    "confidence_level",
    "core_reasons_json",
    "core_payment_anchors_json",
    "supporting_anchors_json",
    "weak_expression_anchors_json",
    "risk_drag_anchors_json",
    "established_anchors_json",
    "proposition_anchors_json",
    "pressure_summary_json",
    "comparison_limitations_json",
    "input_status_json",
    "missing_input_reasons_json",
    "role_downgrade_reasons_json",
    "risk_flags_json",
    "processing_status",
    "review_required",
    "review_status",
    "review_reason_json",
)
ANCHOR_BUSINESS_FIELDS = (
    "sku_code",
    "anchor_code",
    "anchor_rank",
    "role",
    "evidence_strength",
    "confidence",
    "establishment_status",
    "establishment_score",
    "establishment_domains_json",
    "user_validation_status",
    "core_eligible",
    "core_ineligible_reasons_json",
    "pressure_level",
    "pressure_tags_json",
    "pressure_summary_cn",
    "comparison_limitations_json",
    "evidence_domains_json",
    "domain_scores_json",
    "support_summary_cn",
    "weakness_summary_cn",
    "risk_flags_json",
    "role_reason_json",
    "downgrade_reason_code",
)


class G10ReleaseError(RuntimeError):
    pass


def main() -> int:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required.")

    focus_skus = load_focus_skus(Path(args.focus_json))
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    categories: dict[str, Any] = {}
    failures: list[str] = []
    for category in args.categories:
        try:
            with SessionLocal() as db:
                if args.phase in {"dry-run", "write-draft"}:
                    categories[category] = generate_category(
                        db,
                        category=category,
                        focus_skus=focus_skus[category],
                        write=args.phase == "write-draft",
                        detail_limit=args.detail_limit,
                    )
                    if args.phase == "write-draft":
                        db.commit()
                    else:
                        db.rollback()
                elif args.phase == "publish":
                    categories[category] = publish_category(db, category=category)
                    db.commit()
                    categories[category]["post_commit"] = verify_category(
                        db, category=category
                    )
                elif args.phase == "compare-draft":
                    categories[category] = compare_draft_category(
                        db,
                        category=category,
                        focus_skus=focus_skus[category],
                        detail_limit=args.detail_limit,
                    )
                    db.rollback()
                    if categories[category]["difference_count"]:
                        failures.append(
                            f"{category}: draft business result is not reproducible"
                        )
                else:
                    categories[category] = verify_category(db, category=category)
        except Exception as exc:  # noqa: BLE001 - preserve per-category release isolation.
            failures.append(f"{category}: {exc}")
            categories[category] = {"status": "failed", "error": str(exc)}

    engine.dispose()
    payload = {
        "task_id": "M12D-RP-G10",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase,
        "project_id": PROJECT_ID,
        "categories": categories,
        "acceptance": {"passed": not failures, "failures": failures},
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "status": "ok" if not failures else "failed",
                "categories": {
                    category: compact_result(result)
                    for category, result in categories.items()
                },
                "failures": failures,
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failures else 1


def generate_category(
    db: Session,
    *,
    category: str,
    focus_skus: Sequence[str],
    write: bool,
    detail_limit: int,
) -> dict[str, Any]:
    current = current_published_version(db, category)
    sku_codes = current_sku_codes(db, current)
    expected_sku_count = EXPECTED_SKU_COUNTS[category]
    if len(sku_codes) != expected_sku_count:
        raise G10ReleaseError(
            f"current published scope mismatch: {len(sku_codes)} != {expected_sku_count}"
        )
    source_batch_ids = [
        str(value) for value in current.source_batch_ids_json or [] if str(value)
    ]
    if not source_batch_ids:
        raise G10ReleaseError("current version has no source_batch_ids_json")
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    version = PROFILE_VERSIONS[category]
    if write:
        existing_target = db.execute(
            select(entities.Core3PurchaseReasonProfileVersion)
            .where(entities.Core3PurchaseReasonProfileVersion.project_id == PROJECT_ID)
            .where(entities.Core3PurchaseReasonProfileVersion.category_code == category)
            .where(entities.Core3PurchaseReasonProfileVersion.batch_id == current.batch_id)
            .where(
                entities.Core3PurchaseReasonProfileVersion.m12d_profile_version
                == version
            )
            .where(
                entities.Core3PurchaseReasonProfileVersion.rule_version
                == CORE3_M12D_RULE_VERSION
            )
        ).scalar_one_or_none()
        assert_write_target_safe(existing_target, version=version)
    context = Core3RepositoryContext(
        db=db,
        project_id=PROJECT_ID,
        category_code=Core3CategoryCode(category),
    )
    result = PurchaseReasonProfileBatchGenerator(context).generate(
        batch_id=read_scope,
        storage_batch_id=current.batch_id,
        sku_codes=sku_codes,
        product_category=category,
        taxonomy_version=TAXONOMY_VERSIONS[category],
        m12d_profile_version=version,
        write=write,
        generated_by="scripts/m12d_rp_g10_publish_tv_ac.py",
        detail_limit=detail_limit,
        focus_sku_codes=focus_skus,
    )
    evaluation = result.summary["release_quality_evaluation"]
    status_counts = normalized_status_counts(
        evaluation["metrics_json"]["status_counts"]
    )
    assert_release_ready(
        category=category,
        release_quality_status=evaluation["release_quality_status"],
        failure_reason_codes=evaluation["failure_reason_codes"],
        sku_count=result.output_count,
        status_counts=status_counts,
    )
    return {
        "status": "ready",
        "write_mode": "draft" if write else "dry_run",
        "previous_current_version": current.m12d_profile_version,
        "previous_current_version_id": current.purchase_reason_version_id,
        "batch_id": current.batch_id,
        "read_scope": read_scope,
        "source_batch_ids": source_batch_ids,
        "profile_version": version,
        "taxonomy_version": TAXONOMY_VERSIONS[category],
        "sku_count": result.output_count,
        "anchor_count": len(result.anchors),
        "status_counts": status_counts,
        "focus_sku_count": len(focus_skus),
        "release_quality": evaluation,
        "created_output_count": result.created_output_count,
        "updated_output_count": result.updated_output_count,
        "reused_output_count": result.reused_output_count,
        "result_digest": records_digest(result.profiles, result.anchors),
        "business_digest": business_records_digest(result.profiles, result.anchors),
    }


def assert_write_target_safe(existing_version: Any | None, *, version: str) -> None:
    """Keep published/current releases immutable during draft generation."""

    if existing_version is None:
        return
    release_status = str(getattr(existing_version, "release_status", ""))
    is_current = bool(getattr(existing_version, "is_current", False))
    if release_status == M12DReleaseStatus.PUBLISHED.value or is_current:
        raise G10ReleaseError(
            f"write-draft cannot overwrite published/current version: {version}"
        )


def publish_category(db: Session, *, category: str) -> dict[str, Any]:
    version_name = PROFILE_VERSIONS[category]
    current = current_published_version(db, category)
    draft = db.execute(
        select(entities.Core3PurchaseReasonProfileVersion)
        .where(entities.Core3PurchaseReasonProfileVersion.project_id == PROJECT_ID)
        .where(entities.Core3PurchaseReasonProfileVersion.category_code == category)
        .where(entities.Core3PurchaseReasonProfileVersion.batch_id == current.batch_id)
        .where(
            entities.Core3PurchaseReasonProfileVersion.m12d_profile_version
            == version_name
        )
        .where(
            entities.Core3PurchaseReasonProfileVersion.rule_version
            == CORE3_M12D_RULE_VERSION
        )
    ).scalar_one_or_none()
    if draft is None:
        raise G10ReleaseError(f"draft version not found: {version_name}")

    pre = verify_version_rows(db, category=category, version=draft)
    assert_release_ready(
        category=category,
        release_quality_status=str(draft.release_quality_status),
        failure_reason_codes=list(
            (draft.validation_summary_json or {}).get(
                "release_quality_failure_reason_codes"
            )
            or []
        ),
        sku_count=pre["profile_count"],
        status_counts=pre["status_counts"],
    )
    if pre["unassessed_establishment_count"] or pre["unassessed_pressure_count"]:
        raise G10ReleaseError(
            "draft contains unassessed establishment or pressure fields"
        )

    repository = PurchaseReasonProfileRepository(
        Core3RepositoryContext(
            db=db,
            project_id=PROJECT_ID,
            category_code=Core3CategoryCode(category),
        )
    )
    published = repository.publish_version(
        batch_id=current.batch_id,
        m12d_profile_version=version_name,
        rule_version=CORE3_M12D_RULE_VERSION,
        published_by="codex-m12d-rp-g10",
        release_note_cn=(
            "M12D-RP-G10：按当前一致事实线谱重建购买理由成立度、用户承接和购买阻力，"
            "经分品类 release-quality 门禁通过后发布。"
        ),
    )
    return {
        "status": "published_pending_commit",
        "previous_current_version": current.m12d_profile_version,
        "previous_current_version_id": current.purchase_reason_version_id,
        "published_version": published.m12d_profile_version,
        "published_version_id": published.purchase_reason_version_id,
        "pre_publish": pre,
    }


def compare_draft_category(
    db: Session,
    *,
    category: str,
    focus_skus: Sequence[str],
    detail_limit: int,
) -> dict[str, Any]:
    current = current_published_version(db, category)
    sku_codes = current_sku_codes(db, current)
    source_batch_ids = [
        str(value) for value in current.source_batch_ids_json or [] if str(value)
    ]
    read_scope = f"serving-scope:{category}:{','.join(source_batch_ids)}"
    context = Core3RepositoryContext(
        db=db,
        project_id=PROJECT_ID,
        category_code=Core3CategoryCode(category),
    )
    result = PurchaseReasonProfileBatchGenerator(context).generate(
        batch_id=read_scope,
        storage_batch_id=current.batch_id,
        sku_codes=sku_codes,
        product_category=category,
        taxonomy_version=TAXONOMY_VERSIONS[category],
        m12d_profile_version=PROFILE_VERSIONS[category],
        write=False,
        generated_by="scripts/m12d_rp_g10_publish_tv_ac.py",
        detail_limit=detail_limit,
        focus_sku_codes=focus_skus,
    )
    evaluation = result.summary["release_quality_evaluation"]
    status_counts = normalized_status_counts(
        evaluation["metrics_json"]["status_counts"]
    )
    assert_release_ready(
        category=category,
        release_quality_status=evaluation["release_quality_status"],
        failure_reason_codes=evaluation["failure_reason_codes"],
        sku_count=result.output_count,
        status_counts=status_counts,
    )
    draft = db.execute(
        select(entities.Core3PurchaseReasonProfileVersion)
        .where(entities.Core3PurchaseReasonProfileVersion.project_id == PROJECT_ID)
        .where(entities.Core3PurchaseReasonProfileVersion.category_code == category)
        .where(
            entities.Core3PurchaseReasonProfileVersion.m12d_profile_version
            == PROFILE_VERSIONS[category]
        )
        .where(
            entities.Core3PurchaseReasonProfileVersion.rule_version
            == CORE3_M12D_RULE_VERSION
        )
    ).scalar_one_or_none()
    if draft is None:
        raise G10ReleaseError(f"draft version not found: {PROFILE_VERSIONS[category]}")
    draft_profiles, draft_anchors = version_records(db, draft)
    differences = business_records_diff(
        expected_profiles=draft_profiles,
        expected_anchors=draft_anchors,
        actual_profiles=result.profiles,
        actual_anchors=result.anchors,
    )
    return {
        "status": "ready" if not differences["difference_count"] else "drift",
        "profile_version": PROFILE_VERSIONS[category],
        "sku_count": result.output_count,
        "anchor_count": len(result.anchors),
        "status_counts": status_counts,
        "release_quality_status": evaluation["release_quality_status"],
        "draft_business_digest": business_records_digest(
            draft_profiles, draft_anchors
        ),
        "regenerated_business_digest": business_records_digest(
            result.profiles, result.anchors
        ),
        **differences,
    }


def verify_category(db: Session, *, category: str) -> dict[str, Any]:
    current = current_published_version(db, category)
    expected_version = PROFILE_VERSIONS[category]
    if current.m12d_profile_version != expected_version:
        raise G10ReleaseError(
            f"unexpected current version: {current.m12d_profile_version} != {expected_version}"
        )
    result = verify_version_rows(db, category=category, version=current)
    assert_release_ready(
        category=category,
        release_quality_status=str(current.release_quality_status),
        failure_reason_codes=list(
            (current.validation_summary_json or {}).get(
                "release_quality_failure_reason_codes"
            )
            or []
        ),
        sku_count=result["profile_count"],
        status_counts=result["status_counts"],
    )
    current_version_count = db.execute(
        select(func.count())
        .select_from(entities.Core3PurchaseReasonProfileVersion)
        .where(entities.Core3PurchaseReasonProfileVersion.project_id == PROJECT_ID)
        .where(entities.Core3PurchaseReasonProfileVersion.category_code == category)
        .where(entities.Core3PurchaseReasonProfileVersion.batch_id == current.batch_id)
        .where(entities.Core3PurchaseReasonProfileVersion.is_current.is_(True))
    ).scalar_one()
    current_profile_versions = list(
        db.execute(
            select(entities.Core3SkuPurchaseReasonProfile.m12d_profile_version)
            .distinct()
            .where(entities.Core3SkuPurchaseReasonProfile.project_id == PROJECT_ID)
            .where(entities.Core3SkuPurchaseReasonProfile.category_code == category)
            .where(entities.Core3SkuPurchaseReasonProfile.batch_id == current.batch_id)
            .where(entities.Core3SkuPurchaseReasonProfile.is_current.is_(True))
        ).scalars()
    )
    current_anchor_versions = list(
        db.execute(
            select(entities.Core3SkuPurchaseReasonAnchor.m12d_profile_version)
            .distinct()
            .where(entities.Core3SkuPurchaseReasonAnchor.project_id == PROJECT_ID)
            .where(entities.Core3SkuPurchaseReasonAnchor.category_code == category)
            .where(entities.Core3SkuPurchaseReasonAnchor.batch_id == current.batch_id)
            .where(entities.Core3SkuPurchaseReasonAnchor.is_current.is_(True))
        ).scalars()
    )
    if int(current_version_count) != 1:
        raise G10ReleaseError(f"current version count is {current_version_count}")
    if current_profile_versions != [expected_version]:
        raise G10ReleaseError(
            f"current profile versions are {current_profile_versions}"
        )
    if current_anchor_versions != [expected_version]:
        raise G10ReleaseError(f"current anchor versions are {current_anchor_versions}")
    return {
        "status": "published",
        "batch_id": current.batch_id,
        "profile_version": current.m12d_profile_version,
        "version_id": current.purchase_reason_version_id,
        "release_status": current.release_status,
        "release_quality_status": current.release_quality_status,
        "published_at": current.published_at,
        "published_by": current.published_by,
        "current_version_count": int(current_version_count),
        "current_profile_versions": current_profile_versions,
        "current_anchor_versions": current_anchor_versions,
        **result,
    }


def verify_version_rows(
    db: Session,
    *,
    category: str,
    version: entities.Core3PurchaseReasonProfileVersion,
) -> dict[str, Any]:
    profiles, anchors = version_records(db, version)
    status_counts = normalized_status_counts(
        Counter(str(profile.status) for profile in profiles)
    )
    return {
        "profile_count": len(profiles),
        "anchor_count": len(anchors),
        "status_counts": status_counts,
        "unassessed_establishment_count": sum(
            str(anchor.establishment_status) == "unassessed" for anchor in anchors
        ),
        "unassessed_pressure_count": sum(
            str(anchor.pressure_level) == "unassessed" for anchor in anchors
        ),
        "result_digest": records_digest(profiles, anchors),
        "business_digest": business_records_digest(profiles, anchors),
        "category_isolated": all(
            str(profile.category_code) == category
            and str(profile.product_category).upper() == category
            for profile in profiles
        )
        and all(
            str(anchor.category_code) == category
            and str(anchor.product_category).upper() == category
            for anchor in anchors
        ),
    }


def version_records(
    db: Session,
    version: entities.Core3PurchaseReasonProfileVersion,
) -> tuple[list[Any], list[Any]]:
    profiles = list(
        db.execute(
            select(entities.Core3SkuPurchaseReasonProfile).where(
                entities.Core3SkuPurchaseReasonProfile.purchase_reason_version_id
                == version.purchase_reason_version_id
            )
        ).scalars()
    )
    anchors = list(
        db.execute(
            select(entities.Core3SkuPurchaseReasonAnchor).where(
                entities.Core3SkuPurchaseReasonAnchor.purchase_reason_version_id
                == version.purchase_reason_version_id
            )
        ).scalars()
    )
    return profiles, anchors


def current_published_version(
    db: Session, category: str
) -> entities.Core3PurchaseReasonProfileVersion:
    version = db.execute(
        select(entities.Core3PurchaseReasonProfileVersion)
        .where(entities.Core3PurchaseReasonProfileVersion.project_id == PROJECT_ID)
        .where(entities.Core3PurchaseReasonProfileVersion.category_code == category)
        .where(
            entities.Core3PurchaseReasonProfileVersion.release_status
            == M12DReleaseStatus.PUBLISHED.value
        )
        .where(entities.Core3PurchaseReasonProfileVersion.is_current.is_(True))
        .order_by(
            entities.Core3PurchaseReasonProfileVersion.published_at.desc().nullslast()
        )
    ).scalars().first()
    if version is None:
        raise G10ReleaseError(f"current published {category} version not found")
    return version


def current_sku_codes(
    db: Session, version: entities.Core3PurchaseReasonProfileVersion
) -> list[str]:
    return list(
        db.execute(
            select(entities.Core3SkuPurchaseReasonProfile.sku_code)
            .where(
                entities.Core3SkuPurchaseReasonProfile.purchase_reason_version_id
                == version.purchase_reason_version_id
            )
            .order_by(entities.Core3SkuPurchaseReasonProfile.sku_code)
        ).scalars()
    )


def assert_release_ready(
    *,
    category: str,
    release_quality_status: str,
    failure_reason_codes: Sequence[str],
    sku_count: int,
    status_counts: dict[str, int],
) -> None:
    if release_quality_status != M12DReleaseQualityStatus.READY.value:
        raise G10ReleaseError(
            f"release quality is {release_quality_status}: {list(failure_reason_codes)}"
        )
    if failure_reason_codes:
        raise G10ReleaseError(f"release failure reasons: {list(failure_reason_codes)}")
    if sku_count != EXPECTED_SKU_COUNTS[category]:
        raise G10ReleaseError(
            f"SKU count mismatch: {sku_count} != {EXPECTED_SKU_COUNTS[category]}"
        )
    if status_counts != EXPECTED_STATUS_COUNTS[category]:
        raise G10ReleaseError(
            f"status distribution drift: {status_counts} != {EXPECTED_STATUS_COUNTS[category]}"
        )


def load_focus_skus(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {
        category: [
            str(row["sku_code"]).strip().upper()
            for row in payload["categories"][category]["focus_profiles"]
        ]
        for category in ("TV", "AC")
    }
    if len(result["TV"]) != 10 or len(result["AC"]) != 18:
        raise G10ReleaseError(f"unexpected focus SKU scope: {result}")
    return result


def normalized_status_counts(values: Any) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(dict(values).items())
        if int(value)
    }


def records_digest(profiles: Sequence[Any], anchors: Sequence[Any]) -> str:
    material = {
        "profiles": sorted(
            (str(row.sku_code), str(row.result_hash)) for row in profiles
        ),
        "anchors": sorted(
            (str(row.sku_code), str(row.anchor_code), str(row.result_hash))
            for row in anchors
        ),
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def business_records_digest(
    profiles: Sequence[Any], anchors: Sequence[Any]
) -> str:
    """Hash stable business outcomes without run-specific technical fingerprints."""

    material = business_records_material(profiles, anchors)
    return hashlib.sha256(
        json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def business_records_material(
    profiles: Sequence[Any], anchors: Sequence[Any]
) -> dict[str, list[dict[str, Any]]]:
    return {
        "profiles": sorted(
            (_business_row(row, PROFILE_BUSINESS_FIELDS) for row in profiles),
            key=lambda row: row["sku_code"],
        ),
        "anchors": sorted(
            (_business_row(row, ANCHOR_BUSINESS_FIELDS) for row in anchors),
            key=lambda row: (row["sku_code"], row["anchor_code"]),
        ),
    }


def business_records_diff(
    *,
    expected_profiles: Sequence[Any],
    expected_anchors: Sequence[Any],
    actual_profiles: Sequence[Any],
    actual_anchors: Sequence[Any],
    sample_limit: int = 50,
) -> dict[str, Any]:
    expected = business_records_material(expected_profiles, expected_anchors)
    actual = business_records_material(actual_profiles, actual_anchors)
    samples: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for record_type, key_fields in (
        ("profiles", ("sku_code",)),
        ("anchors", ("sku_code", "anchor_code")),
    ):
        expected_by_key = {
            tuple(row[field] for field in key_fields): row
            for row in expected[record_type]
        }
        actual_by_key = {
            tuple(row[field] for field in key_fields): row
            for row in actual[record_type]
        }
        difference_count = 0
        for key in sorted(set(expected_by_key) | set(actual_by_key)):
            expected_row = expected_by_key.get(key)
            actual_row = actual_by_key.get(key)
            if expected_row == actual_row:
                continue
            difference_count += 1
            if len(samples) < sample_limit:
                changed_fields = sorted(
                    field
                    for field in set(expected_row or {}) | set(actual_row or {})
                    if (expected_row or {}).get(field)
                    != (actual_row or {}).get(field)
                )
                samples.append(
                    {
                        "record_type": record_type[:-1],
                        "key": list(key),
                        "changed_fields": changed_fields,
                        "expected_values": {
                            field: _short_value((expected_row or {}).get(field))
                            for field in changed_fields
                        },
                        "actual_values": {
                            field: _short_value((actual_row or {}).get(field))
                            for field in changed_fields
                        },
                    }
                )
        counts[f"{record_type[:-1]}_difference_count"] = difference_count
    return {
        **counts,
        "difference_count": sum(counts.values()),
        "difference_samples": samples,
    }


def _business_row(row: Any, fields: Sequence[str]) -> dict[str, Any]:
    return {field: _canonical_business_value(getattr(row, field, None)) for field in fields}


def _canonical_business_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, (Decimal, float)):
        normalized = Decimal(str(value)).normalize()
        return format(normalized, "f")
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_business_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_business_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _canonical_business_value(value.model_dump(mode="python"))
    return str(value)


def _short_value(value: Any, *, limit: int = 800) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= limit:
        return value
    return encoded[: limit - 3] + "..."


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "failed":
        return result
    post = result.get("post_commit") or result
    return {
        "status": post.get("status"),
        "profile_version": post.get("profile_version")
        or result.get("published_version"),
        "sku_count": post.get("sku_count") or post.get("profile_count"),
        "anchor_count": post.get("anchor_count"),
        "status_counts": post.get("status_counts"),
        "release_quality_status": post.get("release_quality_status")
        or (result.get("release_quality") or {}).get("release_quality_status"),
        "result_digest": post.get("result_digest") or result.get("result_digest"),
        "business_digest": post.get("business_digest")
        or result.get("business_digest"),
        "difference_count": (
            post.get("difference_count")
            if "difference_count" in post
            else result.get("difference_count")
        ),
    }


def json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("dry-run", "write-draft", "compare-draft", "publish", "verify"),
        required=True,
    )
    parser.add_argument("--database-url", default="")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=("TV", "AC"),
        default=["TV", "AC"],
    )
    parser.add_argument("--focus-json", default=str(DEFAULT_FOCUS_PATH))
    parser.add_argument("--detail-limit", type=int, default=50)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
