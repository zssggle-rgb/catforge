from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssetDiff, AssetVersion, CategoryProject
from app.services.audit_service import create_audit_event
from app.services.hardening_utils import now_iso, sha256_json


class VersionGovernanceError(ValueError):
    pass


def create_asset_version(
    db: Session,
    *,
    project_id: str | None,
    asset_type: str,
    category_code: str = "TV",
    version: str,
    manifest_json: dict[str, Any],
    created_by: str = "system",
) -> AssetVersion:
    content_hash = sha256_json(manifest_json)
    row = AssetVersion(
        project_id=project_id,
        asset_type=asset_type,
        category_code=category_code,
        version=version,
        lifecycle_status="draft",
        content_hash=content_hash,
        manifest_json=manifest_json,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    create_audit_event(
        db,
        action="asset_version_created",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=project_id,
        actor_id=created_by,
        after=asset_version_to_dict(row),
        metadata={"asset_type": asset_type, "version": version},
    )
    db.commit()
    db.refresh(row)
    return row


def edit_asset_version(
    db: Session,
    asset_version_id: str,
    *,
    manifest_json: dict[str, Any],
    actor_id: str = "system",
) -> AssetVersion:
    row = _get_asset_version(db, asset_version_id)
    before = asset_version_to_dict(row)
    if row.lifecycle_status == "released":
        new_version = f"{row.version}-draft-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        draft = AssetVersion(
            project_id=row.project_id,
            asset_type=row.asset_type,
            category_code=row.category_code,
            version=new_version,
            lifecycle_status="draft",
            content_hash=sha256_json(manifest_json),
            manifest_json={
                **manifest_json,
                "derived_from_released_version_id": row.asset_version_id,
            },
            created_by=actor_id,
        )
        db.add(draft)
        db.flush()
        create_audit_event(
            db,
            action="asset_edit_created_new_draft",
            object_type="asset_version",
            object_id=draft.asset_version_id,
            project_id=draft.project_id,
            actor_id=actor_id,
            before=before,
            after=asset_version_to_dict(draft),
            metadata={"released_version_id": row.asset_version_id},
        )
        db.commit()
        db.refresh(draft)
        return draft
    if row.lifecycle_status == "archived":
        raise VersionGovernanceError("archived 版本不可编辑")
    row.manifest_json = manifest_json
    row.content_hash = sha256_json(manifest_json)
    create_audit_event(
        db,
        action="asset_version_edited",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=row.project_id,
        actor_id=actor_id,
        before=before,
        after=asset_version_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return row


def submit_asset_review(db: Session, asset_version_id: str, *, actor_id: str = "system") -> AssetVersion:
    row = _get_asset_version(db, asset_version_id)
    before = asset_version_to_dict(row)
    if row.lifecycle_status == "released":
        raise VersionGovernanceError("released 版本不可重新提交评审")
    if row.lifecycle_status == "archived":
        raise VersionGovernanceError("archived 版本不可重新提交评审")
    row.lifecycle_status = "in_review"
    create_audit_event(
        db,
        action="asset_submitted_review",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=row.project_id,
        actor_id=actor_id,
        before=before,
        after=asset_version_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return row


def approve_asset_version(
    db: Session, asset_version_id: str, *, actor_id: str = "system"
) -> AssetVersion:
    row = _get_asset_version(db, asset_version_id)
    before = asset_version_to_dict(row)
    if row.lifecycle_status == "released":
        raise VersionGovernanceError("released 版本不可重复审批")
    if row.lifecycle_status == "archived":
        raise VersionGovernanceError("archived 版本不可审批")
    row.lifecycle_status = "in_review"
    row.approved_by = actor_id
    row.manifest_json = {**(row.manifest_json or {}), "approved": True}
    row.content_hash = sha256_json(row.manifest_json)
    create_audit_event(
        db,
        action="asset_approved",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=row.project_id,
        actor_id=actor_id,
        before=before,
        after=asset_version_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return row


def release_asset_version(
    db: Session,
    asset_version_id: str,
    *,
    actor_id: str = "system",
    approved_by: str | None = None,
) -> AssetVersion:
    row = _get_asset_version(db, asset_version_id)
    before = asset_version_to_dict(row)
    if row.lifecycle_status == "released":
        raise VersionGovernanceError("released 版本不可原地重复发布")
    if row.lifecycle_status == "archived":
        raise VersionGovernanceError("archived 版本不可发布")
    release_time = datetime.utcnow()
    row.approved_by = approved_by or row.approved_by or actor_id
    row.lifecycle_status = "released"
    row.released_at = release_time
    release_manifest = _release_manifest(row, release_time)
    row.manifest_json = release_manifest
    row.content_hash = sha256_json(release_manifest)
    create_audit_event(
        db,
        action="asset_released",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=row.project_id,
        actor_id=actor_id,
        before=before,
        after=asset_version_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return row


def rollback_asset_version(
    db: Session,
    asset_version_id: str,
    *,
    target_version_id: str | None = None,
    reason: str = "",
    actor_id: str = "system",
) -> AssetVersion:
    current = _get_asset_version(db, asset_version_id)
    target = _get_asset_version(db, target_version_id or asset_version_id)
    if target.lifecycle_status != "released":
        raise VersionGovernanceError("只能回滚到 released 版本")
    rollback_version = f"{target.version}-rollback-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    manifest = {
        **(target.manifest_json or {}),
        "rollback_from_version_id": current.asset_version_id,
        "rollback_to_version_id": target.asset_version_id,
        "rollback_reason": reason,
    }
    row = AssetVersion(
        project_id=target.project_id,
        asset_type=target.asset_type,
        category_code=target.category_code,
        version=rollback_version,
        lifecycle_status="released",
        content_hash=sha256_json(manifest),
        manifest_json=manifest,
        created_by=actor_id,
        approved_by=actor_id,
        released_at=datetime.utcnow(),
        rollback_from_version_id=target.asset_version_id,
        rollback_reason=reason,
    )
    db.add(row)
    db.flush()
    create_audit_event(
        db,
        action="asset_rollback",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=row.project_id,
        actor_id=actor_id,
        before=asset_version_to_dict(current),
        after=asset_version_to_dict(row),
        metadata={"target_version_id": target.asset_version_id, "reason": reason},
    )
    db.commit()
    db.refresh(row)
    return row


def archive_asset_version(
    db: Session,
    asset_version_id: str,
    *,
    reason: str = "",
    actor_id: str = "system",
) -> AssetVersion:
    row = _get_asset_version(db, asset_version_id)
    before = asset_version_to_dict(row)
    if row.lifecycle_status == "archived":
        return row
    row.lifecycle_status = "archived"
    row.archived_at = datetime.utcnow()
    row.manifest_json = {**(row.manifest_json or {}), "archive_reason": reason}
    row.content_hash = sha256_json(row.manifest_json)
    create_audit_event(
        db,
        action="asset_archived",
        object_type="asset_version",
        object_id=row.asset_version_id,
        project_id=row.project_id,
        actor_id=actor_id,
        before=before,
        after=asset_version_to_dict(row),
        metadata={"reason": reason},
    )
    db.commit()
    db.refresh(row)
    return row


def list_asset_versions(db: Session, asset_id: str) -> list[AssetVersion]:
    seed = _get_asset_version(db, asset_id)
    rows = db.execute(
        select(AssetVersion)
        .where(
            AssetVersion.project_id == seed.project_id,
            AssetVersion.asset_type == seed.asset_type,
            AssetVersion.category_code == seed.category_code,
        )
        .order_by(AssetVersion.created_at.desc())
    ).scalars().all()
    return list(rows)


def diff_asset_versions(db: Session, from_version: str, to_version: str) -> AssetDiff:
    left = _find_version(db, from_version)
    right = _find_version(db, to_version)
    diff = _dict_diff(left.manifest_json or {}, right.manifest_json or {})
    row = AssetDiff(
        from_version=left.version,
        to_version=right.version,
        diff_json=diff,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def asset_version_to_dict(row: AssetVersion) -> dict[str, Any]:
    return {
        "asset_version_id": row.asset_version_id,
        "project_id": row.project_id,
        "asset_type": row.asset_type,
        "category_code": row.category_code,
        "version": row.version,
        "lifecycle_status": row.lifecycle_status,
        "content_hash": row.content_hash,
        "manifest_json": row.manifest_json,
        "created_by": row.created_by,
        "approved_by": row.approved_by,
        "released_at": now_iso(row.released_at),
        "archived_at": now_iso(row.archived_at),
        "rollback_from_version_id": row.rollback_from_version_id,
        "rollback_reason": row.rollback_reason,
    }


def asset_diff_to_dict(row: AssetDiff) -> dict[str, Any]:
    return {
        "diff_id": row.diff_id,
        "from_version": row.from_version,
        "to_version": row.to_version,
        "diff_json": row.diff_json,
        "created_at": now_iso(row.created_at),
    }


def latest_released_asset_version(db: Session, project_id: str) -> AssetVersion | None:
    return db.execute(
        select(AssetVersion)
        .where(
            AssetVersion.project_id == project_id,
            AssetVersion.lifecycle_status == "released",
        )
        .order_by(AssetVersion.released_at.desc())
    ).scalars().first()


def _release_manifest(row: AssetVersion, release_time: datetime) -> dict[str, Any]:
    manifest = row.manifest_json or {}
    return {
        "asset_version": row.version,
        "category": row.category_code,
        "rule_versions": manifest.get("rule_versions", {}),
        "input_dataset_fingerprint": manifest.get("input_dataset_fingerprint", "unknown"),
        "evaluation_report_id": manifest.get("evaluation_report_id", "unknown"),
        "quality_gates": manifest.get("quality_gates", {}),
        "created_by": row.created_by,
        "approved_by": row.approved_by,
        "release_time": release_time.isoformat(),
        "files": manifest.get("files", []),
        "runtime_files": manifest.get("runtime_files", []),
        "rollback_from_version_id": manifest.get("rollback_from_version_id"),
        "content_hash": sha256_json(
            {
                "version": row.version,
                "manifest": manifest,
                "released_at": release_time.isoformat(),
            }
        ),
        "released_at": release_time.isoformat(),
    }


def _get_asset_version(db: Session, asset_version_id: str | None) -> AssetVersion:
    if not asset_version_id:
        raise VersionGovernanceError("asset_version_id 不能为空")
    row = db.get(AssetVersion, asset_version_id)
    if not row:
        raise VersionGovernanceError("资产版本不存在")
    return row


def _find_version(db: Session, version: str) -> AssetVersion:
    row = db.execute(select(AssetVersion).where(AssetVersion.version == version)).scalars().first()
    if not row:
        row = db.get(AssetVersion, version)
    if not row:
        raise VersionGovernanceError("资产版本不存在")
    return row


def _dict_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    added = {key: right[key] for key in right.keys() - left.keys()}
    removed = {key: left[key] for key in left.keys() - right.keys()}
    changed = {
        key: {"from": left[key], "to": right[key]}
        for key in left.keys() & right.keys()
        if left[key] != right[key]
    }
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
        },
    }
