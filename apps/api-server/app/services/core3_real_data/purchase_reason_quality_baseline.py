"""Read-only TV/AC quality baseline capture for the M12D repair chain."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_AC_RULE_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_AC_RULE_VERSION,
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M12C_RULE_VERSION,
    M12DReleaseStatus,
)


INPUT_STATUS_FIELDS = (
    "param_profile_status",
    "claim_fact_status",
    "comment_profile_status",
    "market_profile_status",
    "semantic_profile_status",
    "semantic_market_status",
    "claim_value_status",
)


def capture_quality_baseline(
    db: Session,
    *,
    project_id: str,
    categories: Sequence[str] = ("TV", "AC"),
) -> dict[str, Any]:
    category_payloads = {
        category_code: _capture_category(db, project_id=project_id, category_code=category_code)
        for category_code in categories
    }
    payload = {
        "project_id": project_id,
        "categories": category_payloads,
    }
    return {**payload, "baseline_fingerprint": baseline_fingerprint(payload)}


def summarize_m12d_records(
    *,
    version: Any,
    profiles: Sequence[Any],
    anchors: Sequence[Any],
) -> dict[str, Any]:
    status_counts = Counter(str(row.status) for row in profiles)
    review_status_counts = Counter(str(getattr(row, "review_status", "unknown")) for row in profiles)
    input_status_counts = {
        field_name: dict(Counter(str(getattr(row, field_name, "unknown")) for row in profiles))
        for field_name in INPUT_STATUS_FIELDS
    }
    profile_risk_flags = _flag_counts(profiles, ("risk_flags_json",))
    anchor_risk_flags = _flag_counts(anchors, ("risk_flags_json",))
    review_reasons = Counter(
        reason
        for row in profiles
        for reason in _reason_values(getattr(row, "review_reason_json", None))
    )
    role_counts = Counter(str(row.role) for row in anchors)
    strength_counts = Counter(str(row.evidence_strength) for row in anchors)
    confidences = [_decimal(row.profile_confidence) for row in profiles]
    core_missing_count = sum(1 for row in profiles if not list(getattr(row, "core_payment_anchors_json", None) or []))
    return {
        "version": {
            "purchase_reason_version_id": str(version.purchase_reason_version_id),
            "batch_id": str(version.batch_id),
            "m12d_profile_version": str(version.m12d_profile_version),
            "rule_version": str(version.rule_version),
            "release_status": str(version.release_status),
            "release_quality_status": str(getattr(version, "release_quality_status", "unassessed")),
            "is_current": bool(version.is_current),
            "source_batch_ids": [str(value) for value in (version.source_batch_ids_json or [])],
        },
        "profile_count": len(profiles),
        "anchor_count": len(anchors),
        "status_counts": dict(status_counts),
        "review_required_count": sum(1 for row in profiles if bool(row.review_required)),
        "review_status_counts": dict(review_status_counts),
        "core_payment_missing_count": core_missing_count,
        "profile_confidence": _number_summary(confidences),
        "input_status_counts": input_status_counts,
        "profile_risk_flags": profile_risk_flags,
        "anchor_role_counts": dict(role_counts),
        "anchor_evidence_strength_counts": dict(strength_counts),
        "anchor_risk_flags": anchor_risk_flags,
        "review_reasons": dict(review_reasons),
    }


def summarize_upstream_rows(
    rows: Sequence[Any],
    *,
    multi_row: bool = False,
    batch_order: Sequence[str] = (),
) -> dict[str, Any]:
    selected = _latest_rows(rows, multi_row=multi_row, batch_order=batch_order)
    sku_codes = {str(row.sku_code) for row in selected}
    result = {
        "row_count": len(selected),
        "sku_count": len(sku_codes),
        "rule_versions": dict(Counter(str(getattr(row, "rule_version", "unknown")) for row in selected)),
        "taxonomy_versions": dict(
            Counter(str(getattr(row, "taxonomy_version", "unknown")) for row in selected if hasattr(row, "taxonomy_version"))
        ),
        "quality_flags": _flag_counts(selected, ("quality_flags", "quality_flags_json")),
        "review_required_sku_count": len(
            {str(row.sku_code) for row in selected if bool(getattr(row, "review_required", False))}
        ),
    }
    if selected and hasattr(selected[0], "conflict_count"):
        result["conflict_count_distribution"] = dict(
            Counter(str(int(getattr(row, "conflict_count", 0) or 0)) for row in selected)
        )
        result["conflict_sku_count"] = len(
            {str(row.sku_code) for row in selected if int(getattr(row, "conflict_count", 0) or 0) > 0}
        )
    if selected and hasattr(selected[0], "sample_status"):
        result["sample_status_counts"] = dict(Counter(str(row.sample_status) for row in selected))
    return result


def baseline_fingerprint(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _capture_category(db: Session, *, project_id: str, category_code: str) -> dict[str, Any]:
    version, selection = _select_version(db, project_id=project_id, category_code=category_code)
    if version is None:
        payload = {"category_code": category_code, "selection": "not_found", "m12d": None, "upstream": {}}
        return {**payload, "category_fingerprint": baseline_fingerprint(payload)}

    profiles = _version_rows(db, entities.Core3SkuPurchaseReasonProfile, version)
    anchors = _version_rows(db, entities.Core3SkuPurchaseReasonAnchor, version)
    sku_codes = {str(row.sku_code) for row in profiles}
    source_batch_ids = _source_batch_ids(version)
    upstream = {
        "M03B": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3SkuParamProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=(entities.Core3SkuParamProfile.rule_version == _module_versions(category_code)["M03B"][1],),
            ),
            batch_order=source_batch_ids,
        ),
        "M04C": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3SkuClaimFactProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=_version_conditions(entities.Core3SkuClaimFactProfile, _module_versions(category_code)["M04C"]),
            ),
            batch_order=source_batch_ids,
        ),
        "M05C": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3SkuCommentFactProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=_version_conditions(entities.Core3SkuCommentFactProfile, _module_versions(category_code)["M05C"]),
            ),
            batch_order=source_batch_ids,
        ),
        "M07": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3SkuMarketProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=(
                    entities.Core3SkuMarketProfile.analysis_window == "full_observed_window",
                    entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION,
                ),
            ),
            batch_order=source_batch_ids,
        ),
        "M09C": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3M09cSkuUserTaskProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=_version_conditions(entities.Core3M09cSkuUserTaskProfile, _module_versions(category_code)["M09C"]),
            ),
            batch_order=source_batch_ids,
        ),
        "M10C": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3M10cSkuTargetGroupProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=_version_conditions(entities.Core3M10cSkuTargetGroupProfile, _module_versions(category_code)["M10C"]),
            ),
            batch_order=source_batch_ids,
        ),
        "M11C": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3SkuValueBattlefieldProfile,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=_version_conditions(entities.Core3SkuValueBattlefieldProfile, _module_versions(category_code)["M11C"]),
            ),
            batch_order=source_batch_ids,
        ),
        "M12C": summarize_upstream_rows(
            _upstream_rows(
                db,
                entities.Core3SkuClaimValueQuantification,
                project_id,
                category_code,
                sku_codes,
                source_batch_ids,
                extra_conditions=(entities.Core3SkuClaimValueQuantification.rule_version == CORE3_M12C_RULE_VERSION,),
            ),
            multi_row=True,
            batch_order=source_batch_ids,
        ),
    }
    payload = {
        "category_code": category_code,
        "selection": selection,
        "m12d": summarize_m12d_records(version=version, profiles=profiles, anchors=anchors),
        "upstream": upstream,
    }
    return {**payload, "category_fingerprint": baseline_fingerprint(payload)}


def _select_version(db: Session, *, project_id: str, category_code: str) -> tuple[Any | None, str]:
    base = (
        select(entities.Core3PurchaseReasonProfileVersion)
        .where(entities.Core3PurchaseReasonProfileVersion.project_id == project_id)
        .where(entities.Core3PurchaseReasonProfileVersion.category_code == category_code)
    )
    published_current = db.execute(
        base.where(entities.Core3PurchaseReasonProfileVersion.release_status == M12DReleaseStatus.PUBLISHED.value)
        .where(entities.Core3PurchaseReasonProfileVersion.is_current.is_(True))
        .order_by(entities.Core3PurchaseReasonProfileVersion.published_at.desc())
    ).scalars().first()
    if published_current is not None:
        return published_current, "current_published"
    published = db.execute(
        base.where(entities.Core3PurchaseReasonProfileVersion.release_status == M12DReleaseStatus.PUBLISHED.value)
        .order_by(entities.Core3PurchaseReasonProfileVersion.published_at.desc())
    ).scalars().first()
    if published is not None:
        return published, "latest_published_fallback"
    latest = db.execute(base.order_by(entities.Core3PurchaseReasonProfileVersion.updated_at.desc())).scalars().first()
    return latest, "latest_any_release_fallback" if latest is not None else "not_found"


def _version_rows(db: Session, model_cls: Any, version: Any) -> list[Any]:
    stmt = (
        select(model_cls)
        .where(model_cls.project_id == version.project_id)
        .where(model_cls.category_code == version.category_code)
        .where(model_cls.batch_id == version.batch_id)
        .where(model_cls.m12d_profile_version == version.m12d_profile_version)
        .where(model_cls.rule_version == version.rule_version)
    )
    return list(db.execute(stmt).scalars())


def _upstream_rows(
    db: Session,
    model_cls: Any,
    project_id: str,
    category_code: str,
    sku_codes: set[str],
    source_batch_ids: Sequence[str],
    *,
    extra_conditions: Sequence[Any] = (),
) -> list[Any]:
    if not sku_codes:
        return []
    stmt = (
        select(model_cls)
        .where(model_cls.project_id == project_id)
        .where(model_cls.category_code == category_code)
        .where(model_cls.sku_code.in_(sku_codes))
    )
    if source_batch_ids:
        stmt = stmt.where(model_cls.batch_id.in_(source_batch_ids))
    if hasattr(model_cls, "is_current"):
        stmt = stmt.where(model_cls.is_current.is_(True))
    for condition in extra_conditions:
        stmt = stmt.where(condition)
    return list(db.execute(stmt).scalars())


def _latest_rows(rows: Sequence[Any], *, multi_row: bool, batch_order: Sequence[str] = ()) -> list[Any]:
    order_map = {str(batch_id): index for index, batch_id in enumerate(batch_order)}
    ordered = sorted(
        rows,
        key=lambda row: (
            order_map.get(str(getattr(row, "batch_id", "")), len(order_map)),
            -getattr(getattr(row, "updated_at", None), "timestamp", lambda: 0.0)(),
        ),
    )
    selected: dict[tuple[str, ...], Any] = {}
    for row in ordered:
        key = [str(row.sku_code)]
        if multi_row:
            for field_name in ("claim_code", "context_type", "context_code", "pool_id"):
                key.append(str(getattr(row, field_name, "")))
        selected.setdefault(tuple(key), row)
    return list(selected.values())


def _module_versions(category_code: str) -> dict[str, tuple[str | None, str]]:
    if category_code == "AC":
        return {
            "M03B": (None, CORE3_M03B_AC_RULE_VERSION),
            "M04C": (CORE3_M04C_AC_TAXONOMY_VERSION, CORE3_M04C_AC_RULE_VERSION),
            "M05C": (CORE3_M05C_AC_TAXONOMY_VERSION, CORE3_M05C_AC_RULE_VERSION),
            "M09C": (CORE3_M09C_AC_TAXONOMY_VERSION, CORE3_M09C_AC_RULE_VERSION),
            "M10C": (CORE3_M10C_AC_TAXONOMY_VERSION, CORE3_M10C_AC_RULE_VERSION),
            "M11C": (CORE3_M11C_AC_TAXONOMY_VERSION, CORE3_M11C_AC_RULE_VERSION),
        }
    return {
        "M03B": (None, CORE3_M03B_RULE_VERSION),
        "M04C": (CORE3_M04C_TV_TAXONOMY_VERSION, CORE3_M04C_TV_RULE_VERSION),
        "M05C": (CORE3_M05C_TV_TAXONOMY_VERSION, CORE3_M05C_TV_RULE_VERSION),
        "M09C": (CORE3_M09C_TV_TAXONOMY_VERSION, CORE3_M09C_TV_RULE_VERSION),
        "M10C": (CORE3_M10C_TV_TAXONOMY_VERSION, CORE3_M10C_TV_RULE_VERSION),
        "M11C": (CORE3_M11C_TV_TAXONOMY_VERSION, CORE3_M11C_TV_RULE_VERSION),
    }


def _version_conditions(model_cls: Any, versions: tuple[str | None, str]) -> tuple[Any, ...]:
    taxonomy_version, rule_version = versions
    conditions = [model_cls.rule_version == rule_version]
    if taxonomy_version is not None and hasattr(model_cls, "taxonomy_version"):
        conditions.append(model_cls.taxonomy_version == taxonomy_version)
    return tuple(conditions)


def _source_batch_ids(version: Any) -> list[str]:
    values = [str(value) for value in (version.source_batch_ids_json or []) if value]
    if str(version.batch_id) not in values:
        values.append(str(version.batch_id))
    return values


def _flag_counts(rows: Iterable[Any], fields: Sequence[str]) -> dict[str, Any]:
    row_counts: Counter[str] = Counter()
    sku_sets: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for field_name in fields:
            for flag in _list_values(getattr(row, field_name, None)):
                normalized = _stable_value(flag)
                row_counts[normalized] += 1
                if hasattr(row, "sku_code"):
                    sku_sets[normalized].add(str(row.sku_code))
    return {
        "row_counts": dict(row_counts),
        "sku_counts": {key: len(value) for key, value in sku_sets.items()},
    }


def _reason_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        reasons = value.get("reasons") or []
        return [_stable_value(reason) for reason in reasons]
    return []


def _list_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _stable_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def _number_summary(values: Sequence[Decimal]) -> dict[str, str]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "min": str(ordered[0]),
        "p25": str(ordered[len(ordered) // 4]),
        "median": str(ordered[len(ordered) // 2]),
        "p75": str(ordered[(len(ordered) * 3) // 4]),
        "max": str(ordered[-1]),
    }
