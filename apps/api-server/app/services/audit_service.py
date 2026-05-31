from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services.hardening_utils import now_iso, sha256_json


def create_audit_event(
    db: Session,
    *,
    action: str,
    object_type: str,
    object_id: str,
    actor_id: str = "system",
    project_id: str | None = None,
    before: Any | None = None,
    after: Any | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = False,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        before_hash=sha256_json(before) if before is not None else None,
        after_hash=sha256_json(after) if after is not None else None,
        metadata_json=metadata or {},
    )
    db.add(event)
    db.flush()
    if commit:
        db.commit()
        db.refresh(event)
    return event


def query_audit_events(
    db: Session,
    *,
    project_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
) -> list[AuditEvent]:
    query = select(AuditEvent)
    if project_id:
        query = query.where(AuditEvent.project_id == project_id)
    if object_type:
        query = query.where(AuditEvent.object_type == object_type)
    if object_id:
        query = query.where(AuditEvent.object_id == object_id)
    if action:
        query = query.where(AuditEvent.action == action)
    return list(db.execute(query.order_by(AuditEvent.created_at.desc())).scalars())


def audit_to_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "audit_id": event.audit_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "project_id": event.project_id,
        "before_hash": event.before_hash,
        "after_hash": event.after_hash,
        "metadata_json": event.metadata_json,
        "created_at": now_iso(event.created_at),
    }
